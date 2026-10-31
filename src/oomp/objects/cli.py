"""Bounded trusted-local navigation; no ambient profile or model invocation."""
from __future__ import annotations

import json
import sys

from oomp.domain.graph import TemporalQuery
from oomp.domain.models import AuthorizedScope
from oomp.storage.errors import StorageError
from .contracts import ObjectMapError
from .service import ObjectMap

COMMANDS=frozenset({'tree','inspect','history','explain','export','build-map','rebuild-map','find'})


def add_commands(subparsers,timestamp):
    for name in sorted(COMMANDS):
        parser=subparsers.add_parser(name,help='bounded source-backed object '+name)
        for key in ('db','tenant','namespace','principal'):
            parser.add_argument('--'+key,required=True)
        parser.add_argument('--json',action='store_true')
        parser.add_argument('--known-at',type=timestamp)
        parser.add_argument('--valid-at',type=timestamp)
        if name in {'inspect','history','explain'}:
            parser.add_argument('object_id')
            parser.add_argument('--show-provenance',action='store_true')
            parser.add_argument('--show-content',action='store_true',help='reveal supporting spans to this trusted local operator')
        if name in {'tree','export'}:
            parser.add_argument('--depth',type=int,default=7)
            parser.add_argument('--limit',type=int,default=100)
        if name=='tree':parser.add_argument('--root')
        if name=='export':parser.add_argument('--redacted',action='store_true',help='always redacted, including when omitted')
        if name in {'build-map','rebuild-map'}:
            parser.add_argument('--limit',type=int,default=100)
            parser.add_argument('--cursor')
        if name=='find':
            parser.add_argument('label')
            parser.add_argument('--limit',type=int,default=50)


def visible(value,*,provenance=False,content=False):
    """Filter at every nesting level, including history and explanation results."""
    if isinstance(value,(list,tuple)):
        return [visible(item,provenance=provenance,content=content) for item in value]
    if not isinstance(value,dict):return value
    result={}
    for key,item in value.items():
        if key in {'tenant_id','namespace','principal_id','reference_id','source_reference'}:continue
        if key in {'source_span','content','canonical_content'} and not content:continue
        if key in {'source_proofs','direct_source_proofs','proof','source_event_ids','source_memory_ids'} and not (provenance or content):continue
        result[key]=visible(item,provenance=provenance,content=content)
    return result


def emit(value,as_json):
    # ASCII JSON is also safe with redirected PowerShell CP1252 output. No ANSI.
    rendered=json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':') if as_json else None,indent=None if as_json else 2)
    if len(rendered.encode('utf-8'))>1_048_576:raise ObjectMapError('object_output_limit')
    print(rendered)


def run(args):
    try:
        scope=AuthorizedScope(tenant_id=args.tenant,namespace=args.namespace,principal_id=args.principal)
        service=ObjectMap(args.db)
        query=TemporalQuery(known_at=args.known_at,valid_at=args.valid_at)
        name=args.memory_command
        if name in {'build-map','rebuild-map'}:
            if args.known_at is not None or args.valid_at is not None:raise ObjectMapError('object_build_temporal_filter_invalid')
            result=getattr(service,'build' if name=='build-map' else 'rebuild')(scope,limit=args.limit,cursor=args.cursor).model_dump(mode='json')
        elif name=='tree':
            result=service.tree(scope,root_id=args.root,max_depth=args.depth,max_nodes=args.limit,max_edges=1000,max_work=10000,query=query).model_dump(mode='json')
        elif name=='inspect':
            obj=service.get_object(scope,args.object_id,query=query)
            if obj is None:raise ObjectMapError('object_not_found')
            parents,parents_more=service.memberships(scope,args.object_id,direction='parents',query=query)
            children,children_more=service.memberships(scope,args.object_id,query=query)
            relations,relations_more=service.relations(scope,args.object_id,query=query)
            result={'object':obj.model_dump(mode='json'),'parents':[e.model_dump(mode='json') for e in parents],
                'children':[e.model_dump(mode='json') for e in children],'relations':[e.model_dump(mode='json') for e in relations],
                'truncated':parents_more or children_more or relations_more}
        elif name=='history':result=service.history(scope,args.object_id,query=query)
        elif name=='explain':result=service.explain(scope,args.object_id,query=query)
        elif name=='export':result=service.export_redacted(scope,max_nodes=args.limit,max_depth=args.depth,query=query)
        elif name=='find':
            objects,more=service.find_objects(scope,args.label,limit=args.limit,query=query)
            result={'objects':[o.model_dump(mode='json') for o in objects],'truncated':more,'matching':'exact_label_or_alias'}
        else:raise ObjectMapError('object_command_invalid')
        if result is None:raise ObjectMapError('object_not_found')
        emit(visible(result,provenance=getattr(args,'show_provenance',False),content=getattr(args,'show_content',False)),args.json)
        return 0
    except (StorageError,OSError,ValueError,TypeError) as error:
        code=error.code if isinstance(error,ObjectMapError) else 'object_operation_failed'
        print(json.dumps({'error':code}),file=sys.stderr)
        return 1
