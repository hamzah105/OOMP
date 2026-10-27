from __future__ import annotations

import csv
import importlib.metadata
import json
import os
import platform
import sqlite3
import subprocess
import sys
from pathlib import Path

from benchmarks.analysis.statistics import aggregate
from benchmarks.contracts import Config, Dataset, canonical_json, digest
from benchmarks.datasets.generate import validate as validate_dataset
from benchmarks.metrics.scoring import DEFINITIONS


def write_json(path,data):
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")


def git_head(path):
    try:return subprocess.check_output(["git","rev-parse","HEAD"],cwd=path,text=True,stderr=subprocess.DEVNULL).strip()
    except (OSError,subprocess.SubprocessError):return None


def metadata(root,trace=None):
    versions={}
    for name in ("oomp-memory","pydantic","pytest","mcp","mcp-types","anyio","httpx2"):
        try:versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:versions[name]=None
    code_files=sorted((root/"benchmarks").rglob("*.py"))
    code_hash=digest({str(p.relative_to(root)).replace("\\","/"):p.read_text(encoding="utf-8") for p in code_files if "results" not in p.parts})
    return {"oomp_commit":git_head(root),"trace_commit":git_head(trace) if trace else None,
        "benchmark_code_hash":code_hash,"working_tree_changes_included_in_code_hash":True,
        "python":sys.version.split()[0],"os":platform.system(),"os_release":platform.release(),
        "architecture":platform.machine(),"logical_cpus":os.cpu_count(),"sqlite":sqlite3.sqlite_version,
        "dependencies":versions,"metric_definitions":DEFINITIONS,
        "privacy":"Public synthetic fixtures only; no environment dump, host name, absolute home directory or credentials.",
        "timing_clock":"perf_counter_ns; milliseconds","rss_scope":"whole benchmark process, cumulative peak; not attributable per method"}


def peak_memory():
    if os.name=="nt":
        try:
            import ctypes
            from ctypes import wintypes
            class Counters(ctypes.Structure):
                _fields_=[("cb",wintypes.DWORD),("PageFaultCount",wintypes.DWORD)]+[(k,ctypes.c_size_t) for k in
                    ("PeakWorkingSetSize","WorkingSetSize","QuotaPeakPagedPoolUsage","QuotaPagedPoolUsage",
                     "QuotaPeakNonPagedPoolUsage","QuotaNonPagedPoolUsage","PagefileUsage","PeakPagefileUsage")]
            c=Counters();c.cb=ctypes.sizeof(c)
            kernel=ctypes.windll.kernel32;kernel.GetCurrentProcess.restype=wintypes.HANDLE
            read_memory=ctypes.windll.psapi.GetProcessMemoryInfo
            read_memory.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
            read_memory.restype=wintypes.BOOL
            if read_memory(kernel.GetCurrentProcess(),ctypes.byref(c),c.cb):
                return {"peak_working_set_bytes":c.PeakWorkingSetSize,"source":"Windows GetProcessMemoryInfo"}
        except (OSError,AttributeError):pass
    try:
        import resource
        scale=1 if sys.platform=="darwin" else 1024
        return {"peak_rss_bytes":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*scale,"source":"getrusage whole process"}
    except ImportError:return {"peak_rss_bytes":None,"source":"unavailable"}


def load_run(directory,allow_partial=False):
    directory=Path(directory);manifest=json.loads((directory/"manifest.json").read_text(encoding="utf-8"))
    if manifest["status"]!="complete" and not allow_partial:raise ValueError("partial run cannot be reported as complete")
    config=Config.model_validate_json((directory/"config.json").read_text(encoding="utf-8"))
    dataset=Dataset.model_validate_json((directory/"dataset.json").read_text(encoding="utf-8"));validate_dataset(dataset)
    if digest(config.model_dump(mode="json"))!=manifest["config_hash"] or digest(dataset.model_dump(mode="json"))!=manifest["dataset_hash"]:
        raise ValueError("frozen input hash mismatch")
    rows=[json.loads(s) for s in (directory/"per_query.jsonl").read_text(encoding="utf-8").splitlines() if s.strip()]
    keys=[(r["case_id"],r["method"],r["repetition"]) for r in rows]
    expected={(c.case_id,m,r) for c in dataset.cases for m in config.methods for r in range(config.repetitions)}
    if len(keys)!=len(set(keys)) or not set(keys)<=expected:raise ValueError("duplicate or unexpected query records")
    if manifest["status"]=="complete" and set(keys)!=expected:raise ValueError("completed run is missing query records")
    if len(rows)!=manifest["records_written"]:raise ValueError("record count mismatch")
    groups={}
    histories={h.history_id:h for h in dataset.histories}
    from benchmarks.datasets.generate import eligible
    expected_sources={c.case_id:digest([e.model_dump(mode="json") for e in eligible(histories[c.history_id],c)]) for c in dataset.cases}
    for row in rows:
        if row["dataset_hash"]!=manifest["dataset_hash"] or row["config_hash"]!=manifest["config_hash"]:
            raise ValueError("record input hash mismatch")
        fingerprint=(row["source_digest"],row["canonical_digest"],row["evidence_budget"])
        previous=groups.setdefault(row["case_id"],fingerprint)
        if fingerprint!=previous:raise ValueError("method source histories or budgets differ")
        if row["source_digest"]!=expected_sources[row["case_id"]] or row["evidence_budget"]!=config.evidence_budget:
            raise ValueError("method did not receive the frozen authorized prefix/budget")
        if row["packet_bytes"]>config.evidence_budget:raise ValueError("budget overflow")
        if row["status"] not in {"ok","unavailable","failed","invalid"}:raise ValueError("unknown status")
    if manifest.get("records_hash") and digest(rows)!=manifest["records_hash"]:
        raise ValueError("query record digest mismatch")
    return manifest,config,dataset,rows


def write_analysis(directory,rows,config,manifest):
    output=aggregate(rows,config);write_json(directory/"aggregate.json",output)
    with (directory/"metrics.csv").open("w",encoding="utf-8",newline="") as stream:
        writer=csv.writer(stream);writer.writerow(("method","metric","mean","ci95_low","ci95_high","cases","histories"))
        for method,data in output["methods"].items():
            for name,metric in data["metrics"].items():
                writer.writerow((method,name,metric["mean"],*(metric["ci95"] or (None,None)),metric["cases"],metric["histories"]))
    lines=[f"# {config.name}","",f"Run status: **{manifest['status']}**. This is an initial synthetic comparison, not a final research evaluation.","",
        "| Method | Queries | Successful | Unavailable | Recall@k | Median first-query ms | Median warm ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for method,data in output["methods"].items():
        metric=data["metrics"].get("recall_at_k",{"mean":None})
        lines.append(f"| {method} | {data['queries']} | {data['status_counts']['ok']} | {data['status_counts']['unavailable']} | {metric['mean']} | {data['latency_ms']['first_query']['median']} | {data['latency_ms']['warm']['median']} |")
    lines += ["","Intervals use seeded history-cluster bootstrap; all cases/repetitions stay in denominators. Unavailable methods are not measured comparisons.",
        "","First-query means the first retrieval on a prepared adapter, not a cold OS/model cache. Method order is rotated deterministically. No generation is included in these retrieval timings.",
        "","Precision uses k even for fewer results. Negative queries have separate empty/false-match metrics. Source rankings flatten canonical proof IDs without duplicate credit.",
        "","Temporal scores assess evidence, not generated state claims. Multi-hop scores require actual returned edge paths and proof; direct lexical endpoint hits alone do not complete a chain.",
        "","The RAM layer uses curated structured observations shared by all canonical baselines. Text grammar/templates are restricted and related across splits. Human answer review and external-system comparisons remain independent work.",
        "","Index, extraction, embedding and summary costs are in corpus_costs.jsonl; add them before amortized performance comparisons. Unobservable internal timings are null, never zero-filled.",
        "","Raw model output is evaluated only when explicitly requested; mocked generator tests are not accuracy measurements.",""]
    (directory/"report.md").write_text("\n".join(lines),encoding="utf-8")
    return output
