"""Opt-in subprocess: invoke TRACE's real generator with controlled live options.

This file lives in OOMP. TRACE source and MongoDB are never written. The wrapper
records/sets evaluation options at the HTTP call seam; it does not mock output.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--workspace",type=Path,required=True)
    args=parser.parse_args(); data=json.load(sys.stdin)
    spec=importlib.util.spec_from_file_location("trace_benchmark_generation",args.workspace/"backend/services/ollama_service.py")
    service=importlib.util.module_from_spec(spec);spec.loader.exec_module(service)
    os.environ["TRACE_OOMP_MODE"]="off"
    service.OLLAMA_URL="http://127.0.0.1:11434/api/generate"
    service.OLLAMA_MODEL=data["model"];service.OLLAMA_TIMEOUT_SECONDS=300
    session=service.requests.Session();session.trust_env=False
    options={"temperature":0.2,"num_predict":140,"num_ctx":data["num_ctx"],"seed":42}
    captured={}
    def live_post(url,*,json,timeout):
        if url!=service.OLLAMA_URL:raise ValueError("nonlocal generation endpoint")
        payload={**json,"options":options}
        response=session.post(url,json=payload,timeout=timeout,allow_redirects=False)
        if response.status_code!=200:raise RuntimeError("local generation failed")
        raw=response.json()
        captured.update({k:raw.get(k) for k in ("model","done","done_reason","prompt_eval_count","eval_count","load_duration","total_duration")})
        return response
    service.requests.post=live_post
    start=time.perf_counter_ns()
    answer=service.generate_response(data["prompt"])
    print(json.dumps({"answer":answer,"generation_ms":(time.perf_counter_ns()-start)/1e6,
                      "effective_options":options,"provider_metadata":captured,"generator":"actual_trace_generate_response"}))


if __name__=="__main__":main()
