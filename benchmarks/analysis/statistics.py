from __future__ import annotations

import random
import statistics
from collections import defaultdict


def percentile(values,p):
    ordered=sorted(values)
    if not ordered:return None
    at=(len(ordered)-1)*p
    lo=int(at);hi=min(lo+1,len(ordered)-1)
    return ordered[lo]+(ordered[hi]-ordered[lo])*(at-lo)


def distribution(values):
    values=list(values);n=len(values)
    return {"n":n,"mean":statistics.mean(values) if n else None,"median":statistics.median(values) if n else None,
        "p95":percentile(values,.95) if n>=20 else None,"p99":percentile(values,.99) if n>=100 else None,
        "stdev":statistics.stdev(values) if n>=2 else None}


def cluster_interval(rows,metric,*,samples=1000,seed=90210):
    clusters=defaultdict(list)
    for row in rows:
        value=row["metrics"].get(metric)
        if value is not None:clusters[row["history_id"]].append(value)
    count=sum(map(len,clusters.values()))
    if not count:return {"mean":None,"ci95":None,"cases":0,"histories":0}
    mean=sum(sum(v) for v in clusters.values())/count
    if len(clusters)<2:return {"mean":mean,"ci95":None,"cases":count,"histories":len(clusters)}
    rng=random.Random(seed); keys=sorted(clusters); means=[]
    for _ in range(samples):
        selected=[clusters[rng.choice(keys)] for _ in keys]
        means.append(sum(sum(v) for v in selected)/sum(map(len,selected)))
    return {"mean":mean,"ci95":[percentile(means,.025),percentile(means,.975)],"cases":count,"histories":len(clusters)}


def aggregate(rows,config):
    output={"methods":{},"paired_effects":{},"interpretation":"Initial synthetic evaluation; confidence intervals do not establish general superiority or statistical significance."}
    metrics=sorted({k for r in rows for k in r["metrics"]})
    for method in config.methods:
        selected=[r for r in rows if r["method"]==method]
        output["methods"][method]={
            "queries":len({r["case_id"] for r in selected}),"records":len(selected),
            "status_counts":{s:sum(r["status"]==s for r in selected) for s in ("ok","unavailable","failed","invalid")},
            "metrics":{m:cluster_interval(selected,m,samples=config.bootstrap_samples,seed=config.bootstrap_seed) for m in metrics},
            "by_category":{c:{m:cluster_interval([r for r in selected if r["category"]==c],m,
                samples=config.bootstrap_samples,seed=config.bootstrap_seed) for m in metrics} for c in sorted({r["category"] for r in selected})},
            "by_task":{c:{m:cluster_interval([r for r in selected if r.get("task_type")==c],m,
                samples=config.bootstrap_samples,seed=config.bootstrap_seed) for m in metrics} for c in sorted({r.get("task_type","unspecified") for r in selected})},
            "by_recent_window":{label:{m:cluster_interval([r for r in selected if r.get("latest_eight_available") is recent],m,
                samples=config.bootstrap_samples,seed=config.bootstrap_seed) for m in metrics} for label,recent in (("inside",True),("outside",False))},
            "latency_ms":{phase:distribution(r["retrieval_ms"] for r in selected if r["status"]=="ok" and r["phase"]==phase) for phase in ("first_query","warm")},
            "context_bytes":distribution(r["packet_bytes"] for r in selected),
        }
    # Pair method differences by (case, repetition), retaining failures as zeros.
    reference={ (r["case_id"],r["repetition"]):r for r in rows if r["method"]=="oomp_full" }
    for method in config.methods:
        if method=="oomp_full":continue
        effects=[]
        for r in rows:
            if r["method"]!=method:continue
            o=reference.get((r["case_id"],r["repetition"]))
            if o and o["metrics"][config.primary_metric] is not None:
                effects.append({"history_id":r["history_id"],"metrics":{
                    "difference":o["metrics"][config.primary_metric]-r["metrics"][config.primary_metric]}})
        output["paired_effects"]["oomp_full-minus-"+method]={
            **cluster_interval(effects,"difference",samples=config.bootstrap_samples,seed=config.bootstrap_seed),
            "comparison_available":all(r["status"]!="unavailable" for r in rows if r["method"] in {method,"oomp_full"}),
            "note":"Unavailable systems remain in denominators but their numerical difference is NOT an executed comparative effect."}
    return output
