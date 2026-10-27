"""Actual Stage 8 MCP/proof/composition study; TRACE and real Mongo stay read-only."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from time import perf_counter_ns

from benchmarks.adapters.corpus import ms, prepare, scope_for
from benchmarks.adapters.memory import FlatLexical
from benchmarks.contracts import History, canonical_json, digest
from benchmarks.datasets.generate import eligible, generate
from benchmarks.reporting import metadata, write_json
from benchmarks.runner import ROOT, load_config, new_directory, now
from oomp.domain.models import MemoryEvent, SourceReference
from oomp.mcp.configuration import Grant, ServerConfiguration
from oomp.retrieval.contracts import MemoryEvidence
from oomp.retrieval.packing import COUNTING_METHOD, pack_evidence


def trace_identity(owner,interaction):
    return "trace-"+hashlib.sha256(json.dumps([owner,interaction,"user"],separators=(",",":")).encode()).hexdigest()


def fixture(history,case):
    owner="stage9-fictional-owner";interactions=[];events=[];id_map={}
    for event in eligible(history,case):
        interaction=hashlib.sha256(event.event_id.encode()).hexdigest()[:24]
        identity=trace_identity(owner,interaction);id_map[event.event_id]=identity
        interactions.append({"_id":interaction,"user_id":owner,"session_id":history.history_id,
            "timestamp":event.ingested_at.isoformat(),"user_message":event.content,"llama_response":"",
            "feedback":{"submitted":False}})
        events.append(MemoryEvent(event_id=identity,tenant_id=history.tenant_id,namespace=history.namespace,
            content=event.content,event_type="user_message",source_type="user",occurred_at=event.occurred_at,
            ingested_at=event.ingested_at,idempotency_key=identity,
            source_reference=SourceReference(source_system="trace-ai",external_event_id=interaction,timestamp=event.occurred_at,
                session_id="trace-session-"+hashlib.sha256(history.history_id.encode()).hexdigest(),turn_id="trace-user-"+interaction),
            metadata={"synthetic":True}))
    return owner,interactions,history.model_copy(update={"events":tuple(events),"curated":(),"links":(),"topics":()}),id_map


def compare(config,trace_workspace,output):
    trace=Path(trace_workspace)
    executable=trace/".venv/Scripts/python.exe"
    if not executable.is_file():raise ValueError("TRACE optional environment unavailable")
    dataset=generate(config)
    history=next((h for h in dataset.histories if h.category=="long_history" and len(h.events)>=128),None)
    if history is None:raise ValueError("TRACE context demo requires a long_history fixture of at least 128 interactions")
    selected=[c for c in dataset.cases if c.history_id==history.history_id]
    directory=new_directory(output,"trace-context")
    write_json(directory/"config.json",config.model_dump(mode="json"))
    write_json(directory/"dataset.json",dataset.model_dump(mode="json"))
    manifest={"status":"running","started_at":now(),"layer":"actual_TRACE_MCP_proof_and_context_functions",
        "metadata":metadata(ROOT,trace),"dataset_hash":digest(dataset.model_dump(mode="json")),
        "config_hash":digest(config.model_dump(mode="json")),"history_id":history.history_id,
        "history_size":len(history.events),"cases":len(selected),"generation_status":"not_executed",
        "MongoDB":"synthetic in-memory mongomock only; no real MongoDB client",
        "http_chat_route_and_owner_login":"not_executed","evidence_budget":config.evidence_budget,
        "total_prompt_byte_cap":config.prompt_budget,"graph_depth":0,"records_written":0}
    write_json(directory/"manifest.json",manifest)
    owner,interactions,normalized,mapping=fixture(history,selected[0])
    source_case=selected[0].model_copy(update={"relevant_source_event_ids":tuple(mapping[x] for x in selected[0].relevant_source_event_ids)})
    prepared,costs,edges=prepare(normalized,source_case,directory/"synthetic.sqlite3")
    manifest.update(synthetic_trace_source_digest=prepared.source_digest,source_transform_version="trace-normalization-v1")
    write_json(directory/"preparation.json",costs)
    flat=FlatLexical(prepared,config,directory/"flat.sqlite3")
    cases=[]
    for case in selected:
        result=flat.retrieve(case)
        items=[] if not result.packet else json.loads(result.packet)["memories"]
        # The real TRACE composer accepts positive-ranked evidence only. Use the
        # flat baseline's existing rank order, not a new relevance calibration.
        memories=[MemoryEvidence.model_validate(item).model_copy(update={"retrieval_score":1/(i+1)}) for i,item in enumerate(items)]
        packed=pack_evidence(memories,config.evidence_budget,config.max_results)
        wire={"retrieval_id":"stage9-flat-"+digest(case.case_id)[:32],
            "memories":[m.model_dump(mode="json") for m in packed.memories],
            "source_references":[r.model_dump(mode="json") for m in packed.memories for r in m.source_references],
            "graph_paths":[],"estimated_token_count":packed.estimated_token_count,"token_budget":config.evidence_budget,
            "counting_method":COUNTING_METHOD,"context_packet":packed.context_packet,"retrieval_mode":"lexical",
            "degraded":False,"warnings":[],"retrieval_trace":{},"source_data_untrusted":True,"budget_scope":"context_packet_only"}
        cases.append({"case_id":case.case_id,"query":case.query,"flat_wire":wire,
            "expected_source_ids":[mapping[s] for s in case.relevant_source_event_ids]})
    flat.close()
    with socket.socket() as listener:listener.bind(("127.0.0.1",0));port=listener.getsockname()[1]
    token=secrets.token_urlsafe(32);owner_key=secrets.token_urlsafe(32)
    server_config=ServerConfiguration(database=str((directory/"synthetic.sqlite3").resolve()),transport="streamable-http",port=port,
        http_grants=(Grant(grant_id="stage9-read",principal_id="stage9-trace-host",tenant_id=history.tenant_id,
            namespace=history.namespace,bearer_token_env="STAGE9_TRACE_TOKEN"),))
    config_path=directory/"mcp-server.json";write_json(config_path,server_config.model_dump(mode="json"))
    payload={"history_id":history.history_id,"interactions":interactions,
        "cases":[{k:v for k,v in case.items() if k!="expected_source_ids"} for case in cases],
        "configuration":{"mode":"retrieve","url":f"http://127.0.0.1:{port}/mcp","owner_id":owner,
            "tenant_id":history.tenant_id,"namespace":history.namespace,"principal_id":"stage9-trace-host",
            "read_token":token,"owner_key":owner_key,"evidence_budget":config.evidence_budget,
            "max_results":config.max_results,"max_prompt_bytes":config.prompt_budget,"num_ctx":config.num_ctx,
            "generation_reserve":config.generation_reserve,"source_system":"trace-ai","retrieval_mode":"lexical"}}
    environment=dict(os.environ,PYTHONDONTWRITEBYTECODE="1",STAGE9_TRACE_TOKEN=token,TRACE_OOMP_MODE="off")
    process=None;start=perf_counter_ns()
    try:
        with (directory/"server.log").open("w",encoding="utf-8") as log:
            process=subprocess.Popen([sys.executable,"-B","-m","oomp","mcp","serve","--config",str(config_path.resolve()),
                "--transport","streamable-http"],cwd=ROOT,env=environment,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=log)
            deadline=time.monotonic()+45
            while True:
                if process.poll() is not None:raise RuntimeError("synthetic MCP server exited")
                try:
                    with socket.create_connection(("127.0.0.1",port),timeout=.25):break
                except OSError:
                    if time.monotonic()>=deadline:raise RuntimeError("synthetic MCP startup timeout")
                    time.sleep(.1)
            worker=Path(__file__).parent/"adapters/trace_context_worker.py"
            result=subprocess.run([str(executable),"-B",str(worker),"--workspace",str(trace)],
                input=canonical_json(payload),text=True,encoding="utf-8",capture_output=True,cwd=ROOT,env=environment,timeout=120)
            if result.returncode:raise RuntimeError("read-only TRACE context bridge failed")
            data=json.loads(result.stdout)
            if len(data["rows"])!=len(cases) or not all(r["same_recent_eight"] and r["source_proof_validated"] for r in data["rows"]):
                raise RuntimeError("TRACE paired context invariant failed")
            for row,case,original in zip(data["rows"],cases,selected,strict=True):
                truth=set(case["expected_source_ids"])
                row.update(expected_source_ids=case["expected_source_ids"],latest_eight_available=original.latest_eight_available,
                    source_recall=len(truth & set(row["retrieved_source_ids"]))/len(truth))
            with (directory/"trace_context.jsonl").open("x",encoding="utf-8") as stream:
                for row in data["rows"]:stream.write(canonical_json(row)+"\n")
            manifest.update(status="complete",records_written=len(data["rows"]),records_hash=digest(data["rows"]),
                generation_calls=0,protocols=sorted({r["protocol"] for r in data["rows"]}))
    except BaseException:
        manifest.update(status="failed",error_code="trace_context_experiment_failed")
        raise
    finally:
        if process is not None:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
        manifest.update(finished_at=now(),elapsed_ms=ms(start))
        write_json(directory/"manifest.json",manifest)
    return directory,manifest


def main(argv=None):
    parser=argparse.ArgumentParser(description="Opt-in actual TRACE/MCP synthetic context comparison; no generation or real MongoDB.")
    parser.add_argument("--config",type=Path,required=True);parser.add_argument("--trace-workspace",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True);args=parser.parse_args(argv)
    try:
        directory,manifest=compare(load_config(args.config),args.trace_workspace,args.output)
        print(json.dumps({"output":str(directory),"status":manifest["status"],"records":manifest["records_written"]}));return 0
    except (ValueError,OSError,RuntimeError):
        print("Synthetic TRACE context comparison unavailable or failed; no real conversation database is used.",file=sys.stderr);return 1


if __name__=="__main__":raise SystemExit(main())
