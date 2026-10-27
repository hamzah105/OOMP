"""Run/validate frozen synthetic comparisons: python -m benchmarks.runner --help."""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter_ns
from uuid import uuid4

from benchmarks.adapters.corpus import ms, prepare, scope_for
from benchmarks.adapters.live import embedding_provider, inventory
from benchmarks.adapters.memory import FlatLexical, FlatVector, LatestEight, OOMP, RollingSummary
from benchmarks.adapters.trace import controlled_prompt, trace_generate
from benchmarks.contracts import Config, Result, canonical_json, digest
from benchmarks.datasets.generate import eligible, generate
from benchmarks.metrics.scoring import answer_scores, score, source_ranking, validate_result
from benchmarks.reporting import git_head, load_run, metadata, peak_memory, write_analysis, write_json

ROOT=Path(__file__).resolve().parents[1]


def now():return datetime.now(timezone.utc).isoformat()


def new_directory(output,name):
    path=Path(output) if output else ROOT/"benchmarks/results"/(name+"-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")+"-"+uuid4().hex[:8])
    # Never reuse an existing run, including a partial one. No ambiguous resume.
    path.mkdir(parents=True,exist_ok=False)
    return path


def load_config(path):return Config.model_validate_json(Path(path).read_text(encoding="utf-8"))


def plan(config):
    dataset=generate(config)
    prefixes={(c.history_id,min(c.history_cutoff,c.known_at or c.history_cutoff)) for c in dataset.cases}
    return {"histories":len(dataset.histories),"cases":len(dataset.cases),"knowledge_prefix_databases":len(prefixes),
        "source_events":sum(len(h.events) for h in dataset.histories),"methods":list(config.methods),
        "retrieval_records":len(dataset.cases)*len(config.methods)*config.repetitions,
        "max_generation_calls":config.max_generation_calls,"query_concurrency":1,"no_model_downloads":True,
        "live_embeddings":"requires --enable-embeddings","live_generation":"separate answer action requires --enable-generation"}


def run(config,output=None,enable_embeddings=False):
    dataset=generate(config); directory=new_directory(output,config.name)
    write_json(directory/"config.json",config.model_dump(mode="json"))
    write_json(directory/"dataset.json",dataset.model_dump(mode="json"))
    manifest={"schema_version":1,"run_name":config.name,"status":"running","started_at":now(),
        "config_hash":digest(config.model_dump(mode="json")),"dataset_hash":digest(dataset.model_dump(mode="json")),
        "dataset_version":dataset.version,"plan":plan(config),"records_written":0,"seeds":list(config.seeds),
        "repetitions":config.repetitions,"split":config.split,"metadata":metadata(ROOT),
        "evidence_budget":config.evidence_budget,"max_results":config.max_results,"metric_k":config.metric_k,
        "temporal_policy":"Materialize only the authorized knowledge prefix; map explicit known_at to actual post-replay storage clock. Valid_at uses authored fixture validity.",
        "generation_status":"not_requested","trace_execution":"pending_read_only_optional_bridge",
        "independent_histories":len(dataset.histories),"model_calls_opt_in":enable_embeddings,
        "unobserved_timings":["independent_canonicalization","trigger_lexical_index","internal_OOMP_packing","MCP_transport"],
        "preregistered_primary_metric":config.primary_metric,"aggregation":config.aggregation}
    write_json(directory/"manifest.json",manifest)
    provider,embedding_meta=embedding_provider(config,enable_embeddings)
    manifest["embedding"]=embedding_meta;write_json(directory/"manifest.json",manifest)
    histories={h.history_id:h for h in dataset.histories}; rows=[]; corpus_records=[]; preparation_cache={};adapter_cache={}
    started=perf_counter_ns(); status="complete"
    try:
        with (directory/"per_query.jsonl").open("x",encoding="utf-8") as stream, (directory/"corpus_costs.jsonl").open("x",encoding="utf-8") as costs_stream:
            for case_index,case in enumerate(dataset.cases):
                history=histories[case.history_id]
                key=(history.history_id,digest([e.model_dump(mode="json") for e in eligible(history,case)]))
                if key not in preparation_cache:
                    corpus_id="corpus-"+digest(key)[:20];db=directory/"databases"/(corpus_id+".sqlite3")
                    prepared,costs,edges=prepare(history,case,db)
                    preparation_cache[key]=(prepared,db,edges)
                    record={"corpus_id":corpus_id,"history_id":history.history_id,
                        "source_digest":prepared.source_digest,"canonical_digest":prepared.canonical_digest,
                        "common_preprocessing":costs,"adapters":{}}
                    if provider is not None:
                        start=perf_counter_ns()
                        report=OOMP(history,prepared,config,db,provider=provider).engine.index(scope_for(history),include_embeddings=True)
                        record["oomp_embedding_index"]={"wall_ms":ms(start),"indexed":report.embeddings_indexed,
                            "failed":report.embeddings_failed,"failure_code":report.failure_code,
                            "space":provider.space.model_dump(mode="json")}
                    adapters={}
                    for method in config.methods:
                        try:
                            if method=="trace_n8":adapter=LatestEight(prepared,config)
                            elif method=="rolling_summary":adapter=RollingSummary(prepared,config)
                            elif method=="flat_lexical":adapter=FlatLexical(prepared,config,directory/"databases"/(corpus_id+"-flat.sqlite3"))
                            elif method=="flat_vector":adapter=FlatVector(prepared,config,provider)
                            else:adapter=OOMP(history,prepared,config,db,method,provider)
                            adapters[method]=adapter
                            record["adapters"][method]=getattr(adapter,"costs",{})
                        except Exception:
                            # Construction failures remain one failed record for EACH
                            # scheduled query, never disappear from the denominator.
                            adapters[method]=None;record["adapters"][method]={"status":"adapter_initialization_failed"}
                    adapter_cache[key]=adapters;corpus_records.append(record)
                    costs_stream.write(canonical_json(record)+"\n");costs_stream.flush()
                prepared,db,edges=preparation_cache[key];adapters=adapter_cache[key]
                methods=list(config.methods)
                # Fixed Latin-style rotation reduces systematic method-order bias.
                rotation=case_index%len(methods);methods=methods[rotation:]+methods[:rotation]
                for repetition in range(config.repetitions):
                    for method in methods:
                        adapter=adapters[method]
                        start=perf_counter_ns()
                        if adapter is None:
                            result=Result(method=method,status="failed",error_code="adapter_initialization_failed")
                        else:
                            try:result=adapter.retrieve(case)
                            except Exception:result=Result(method=method,status="failed",error_code="retrieval_failed",retrieval_ms=ms(start))
                        try:validate_result(result,prepared,config)
                        except Exception:
                            result=Result(method=method,status="invalid",error_code="comparison_invariant_failed",retrieval_ms=result.retrieval_ms)
                        metric=score(case,result,prepared,config,edges)
                        phase="warm" if any(r["method"]==method and r["source_digest"]==prepared.source_digest for r in rows) else "first_query"
                        row={"schema_version":1,"case_id":case.case_id,"history_id":case.history_id,"category":case.category,
                            "task_type":case.case_id.removeprefix(case.history_id+"-"),"indexed_source_count":len(prepared.events),
                            "seed":history.seed,"history_size":len(history.events),"repetition":repetition,"phase":phase,
                            "latest_eight_available":case.latest_eight_available,"fact_distance":case.fact_distance,
                            "fixture_layer":case.fixture_layer,"semantic_label":case.semantic_label,
                            "history_cutoff":case.history_cutoff.isoformat(),"known_at":None if case.known_at is None else case.known_at.isoformat(),
                            "actual_replay_known_at":prepared.replay_known_at.isoformat() if case.known_at else None,
                            "required_hops":case.required_hops,"configured_graph_depth":config.graph_depth,
                            "scope_policy":"same_pinned_synthetic_tenant_namespace_user_sources",
                            "source_digest":prepared.source_digest,"canonical_digest":prepared.canonical_digest,
                            "evidence_budget":config.evidence_budget,"dataset_hash":manifest["dataset_hash"],"config_hash":manifest["config_hash"],
                            **result.model_dump(mode="json"),"ranked_source_ids":list(source_ranking(result.evidence)),"metrics":metric}
                        rows.append(row);stream.write(canonical_json(row)+"\n");stream.flush()
                        manifest["records_written"]=len(rows)
                        write_json(directory/"manifest.json",manifest)
            if enable_embeddings and embedding_meta.get("status")=="ready":
                after=inventory().get(config.embedding_model,{})
                if after.get("digest")!=embedding_meta.get("digest"):
                    status="invalid_model_changed"
    except KeyboardInterrupt:status="interrupted"
    except Exception:
        status="failed";manifest["error_code"]="run_execution_failed"
        raise
    finally:
        for adapters in adapter_cache.values():
            for adapter in adapters.values():
                if hasattr(adapter,"close"):adapter.close()
        manifest.update(status="analyzing" if status=="complete" else status,finished_at=now(),records_written=len(rows),records_hash=digest(rows),
            elapsed_ms=ms(started),memory=peak_memory(),corpus_count=len(corpus_records))
        manifest["comparison_valid"]=not any(r["status"] in {"invalid","failed"} for r in rows)
        write_json(directory/"manifest.json",manifest)
    # Input and rectangular-record validation must pass before a completed report.
    load_run(directory,allow_partial=True)
    if status=="complete" and len(rows)!=len(dataset.cases)*len(config.methods)*config.repetitions:
        raise ValueError("run is missing scheduled query records")
    try:
        write_analysis(directory,rows,config,{**manifest,"status":status})
    except BaseException as error:
        manifest.update(status="interrupted" if isinstance(error,KeyboardInterrupt) else "analysis_failed",error_code="analysis_incomplete")
        write_json(directory/"manifest.json",manifest)
        raise
    manifest["status"]=status
    write_json(directory/"manifest.json",manifest)
    if status=="complete":load_run(directory)
    return directory,manifest


def answers(run_directory,output,trace_workspace,enabled):
    if not enabled:raise ValueError("live generation requires explicit --enable-generation")
    manifest,config,dataset,rows=load_run(run_directory)
    if config.max_generation_calls<len(config.methods):raise ValueError("pre-registered model call limit cannot hold a complete paired case")
    models=inventory()
    if config.generator_model not in models:raise ValueError("live generation model unavailable; no model is downloaded")
    trace=Path(trace_workspace)
    if not (trace/"backend/services/ollama_service.py").is_file():raise ValueError("TRACE workspace unavailable")
    directory=new_directory(output,config.name+"-answers")
    by_key={(r["case_id"],r["method"]):r for r in rows if r["repetition"]==0}
    rng=random.Random(config.bootstrap_seed);selected=list(dataset.cases);rng.shuffle(selected)
    selected=selected[:config.max_generation_calls//len(config.methods)]
    info={"status":"running","layer":"controlled_evidence_generation_via_actual_TRACE_function",
        "production_TRACE_MCP_prompt_pipeline":"pending; this controlled layer does not execute Stage 8 provenance validation or MongoDB",
        "source_run_dataset_hash":manifest["dataset_hash"],"source_run_config_hash":manifest["config_hash"],
        "started_at":now(),"case_ids":[c.case_id for c in selected],"expected_records":len(selected)*len(config.methods),
        "trace_commit":git_head(trace),"model":models[config.generator_model],"records_written":0,
        "options":{"temperature":0.2,"num_predict":140,"num_ctx":config.num_ctx,"seed":42},
        "context_policy":"same neutral instruction, evidence-only for each method; no extra recent window added to retrieval methods",
        "prompt_byte_cap":config.prompt_budget,"requires_blinded_human_review":True}
    write_json(directory/"manifest.json",info); answer_rows=[]
    try:
        with (directory/"answers.jsonl").open("x",encoding="utf-8") as stream:
            for case in selected:
                for method in config.methods:
                    source=by_key[(case.case_id,method)]
                    result=Result.model_validate({k:source[k] for k in Result.model_fields})
                    row={"case_id":case.case_id,"method":method,"status":"failed","answer":"","generation_ms":None}
                    try:
                        if source["status"]!="ok":raise RuntimeError("retrieval unavailable")
                        prompt=controlled_prompt(case,result,config.prompt_budget)
                        generated=trace_generate(trace,prompt,config)
                        row.update(generated,status="ok",prompt=prompt,prompt_bytes=len(prompt.encode("utf-8")))
                    except Exception:row["error_code"]="generation_or_retrieval_unavailable"
                    row["metrics"]=answer_scores(row["answer"],case.expected_answers,case.answerability,
                        source["ranked_source_ids"],row["status"])
                    answer_rows.append(row);stream.write(canonical_json(row)+"\n");stream.flush()
                    info["records_written"]=len(answer_rows);write_json(directory/"manifest.json",info)
        info["status"]="complete" if inventory().get(config.generator_model,{}).get("digest")==models[config.generator_model].get("digest") else "invalid_model_changed"
    except KeyboardInterrupt:info["status"]="interrupted"
    finally:
        info.update(finished_at=now(),records_hash=digest(answer_rows),records_written=len(answer_rows))
        write_json(directory/"manifest.json",info)
    return directory,info


def main(argv=None):
    parser=argparse.ArgumentParser(description="Bounded synthetic OOMP research evaluation; live models are opt-in.")
    parser.add_argument("--action",choices=("plan","generate","run","validate","aggregate","answer"),default="run")
    parser.add_argument("--config",type=Path)
    parser.add_argument("--output",type=Path,help="new output directory; existing paths are refused")
    parser.add_argument("--run",type=Path,help="existing completed run for validation/analysis/answer generation")
    parser.add_argument("--allow-partial",action="store_true",help="inspect partial records with a visible incomplete label")
    parser.add_argument("--enable-embeddings",action="store_true")
    parser.add_argument("--enable-generation",action="store_true")
    parser.add_argument("--trace-workspace",type=Path)
    args=parser.parse_args(argv)
    try:
        if args.action in {"plan","generate","run"}:
            if args.config is None:raise ValueError("--config is required")
            config=load_config(args.config)
            if args.action=="plan":print(json.dumps(plan(config)));return 0
            if args.action=="generate":
                directory=new_directory(args.output,config.name+"-dataset")
                dataset=generate(config);write_json(directory/"dataset.json",dataset.model_dump(mode="json"))
                write_json(directory/"config.json",config.model_dump(mode="json"))
                write_json(directory/"dataset-manifest.json",{"dataset_hash":digest(dataset.model_dump(mode="json")),"config_hash":digest(config.model_dump(mode="json"))})
                print(str(directory));return 0
            directory,manifest=run(config,args.output,args.enable_embeddings)
            print(json.dumps({"output":str(directory),"status":manifest["status"],"records":manifest["records_written"],"comparison_valid":manifest["comparison_valid"]}))
            return 0 if manifest["status"]=="complete" and manifest["comparison_valid"] else 1
        if args.run is None:raise ValueError("--run is required")
        if args.action=="answer":
            if args.trace_workspace is None:raise ValueError("--trace-workspace is required")
            directory,manifest=answers(args.run,args.output,args.trace_workspace,args.enable_generation)
            print(json.dumps({"output":str(directory),"status":manifest["status"]}));return 0 if manifest["status"]=="complete" else 1
        manifest,config,dataset,rows=load_run(args.run,args.allow_partial)
        if args.action=="validate":print(json.dumps({"valid":True,"status":manifest["status"],"records":len(rows)}));return 0
        directory=new_directory(args.output,config.name+"-analysis")
        write_analysis(directory,rows,config,manifest)
        write_json(directory/"source-manifest.json",manifest)
        print(str(directory));return 0
    except (ValueError,OSError):
        print("Benchmark command failed: invalid inputs, unavailable dependency or output already exists. No model is downloaded.",file=sys.stderr)
        return 1


if __name__=="__main__":raise SystemExit(main())
