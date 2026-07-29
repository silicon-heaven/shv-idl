#!/usr/bin/env python3
"""
SHV IDL Parser - Generate TypeScript + Zod code from SHV IDL YAML definition

Generates a single TypeScript file to stdout that:
- imports zod helpers from 'libshv-js-zod'
- declares Zod schemas and TS types for IDL types
- builds an `api` object using `makeRpcCall` / `makeRpcCallParam

Usage:
  python3 shv_idl_generate_typescript.py --config config.yaml < idl.yaml > generated.ts
"""
import argparse
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, TextIO

import yaml

PRIMITIVE_TS = {
    'Null': 'z.undefined()',
    'Int': 'z.number()',
    'Double': 'z.double()',
    'Decimal': 'z.decimal()',
    'String': 'z.string()',
    'Blob': 'z.blob()',
    'Bool': 'z.boolean()',
}

@dataclass
class Field:
    name: str
    type_name: str
    optional: bool = False
    bits: Optional[List[int]] = None

@dataclass
class Variant:
    name: str
    type_name: Optional[str] = None
    value: Optional[int] = None

@dataclass
class TypeDef:
    name: str

@dataclass
class StructType(TypeDef):
    fields: List[Field] = field(default_factory=list)

@dataclass
class TupleType(TypeDef):
    fields: List[str] = field(default_factory=list)

@dataclass
class UnionType(TypeDef):
    variants: List[Variant] = field(default_factory=list)
    tag: Optional[str] = None

@dataclass
class ListType(TypeDef):
    values_type: str = 'String'
    max_size: Optional[int] = None

@dataclass
class MapType(TypeDef):
    values_type: str = 'String'
    values_optional: bool = False

@dataclass
class IMapType(TypeDef):
    values_type: str = 'String'
    values_optional: bool = False

@dataclass
class BitfieldType(TypeDef):
    fields: List[Field] = field(default_factory=list)

@dataclass
class EnumType(TypeDef):
    variants: List[Variant] = field(default_factory=list)

@dataclass
class ErrorType(TypeDef):
    variants: List[Variant] = field(default_factory=list)

@dataclass
class ExternType(TypeDef):
    pass

@dataclass
class IntType(TypeDef):
    min: Optional[int] = None
    max: Optional[int] = None

@dataclass
class DoubleType(TypeDef):
    min: Optional[float] = None
    max: Optional[float] = None

@dataclass
class DecimalType(TypeDef):
    min: Optional[float] = None
    max: Optional[float] = None

@dataclass
class Method:
    name: str
    path_pattern: Optional[str] = None
    method_name: Optional[str] = None
    param: Optional[str] = None
    param_opt: Optional[str] = None
    result: Optional[str] = None
    result_opt: Optional[str] = None
    error: Optional[str] = None
    access: Optional[str] = None
    is_getter: bool = False
    user_id_required: bool = False
    signals: Optional[Dict] = None
    description: Optional[str] = None

@dataclass
class NodeDef:
    name: str
    methods: List[str] = field(default_factory=list)
    tree: Dict[str, str] = field(default_factory=dict)

def to_pascal_case(name: str) -> str:
    parts = re.findall(r'[A-Z]+(?=[A-Z][a-z]|[0-9]|\b)|[A-Z]?[a-z]+|[0-9]+', name)
    return ''.join(part.capitalize() for part in parts)

def to_snake_case(name: str) -> str:
    name = re.sub(r'[^A-Za-z0-9]+', '_', name)
    name = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', name)
    name = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name)
    return re.sub(r'_+', '_', name).strip('_').lower()

def to_camel_case(name: str) -> str:
    parts = [part for part in name.split('_') if part]
    if not parts:
        return ''
    return parts[0] + ''.join(part.capitalize() for part in parts[1:])

def struct_wire_key(name: str) -> str:
    return to_camel_case(to_snake_case(name))

def parse_yaml(stream: TextIO) -> tuple[Dict[str, TypeDef], Dict[str, Method], Dict[str, str], Dict[str, NodeDef]]:
    data = yaml.load(stream, Loader=yaml.SafeLoader)

    types: Dict[str, TypeDef] = {}
    type_defs = data.get('types', {})

    for name, defn in type_defs.items():
        type_name = defn.get('type', '')

        if type_name == 'Struct':
            fields = []
            for f in defn.get('fields', []):
                field_type = f.get('type', 'String')
                is_optional = f.get('optional', False) or 'type_opt' in f
                if 'type_opt' in f:
                    is_optional = True
                    field_type = f.get('type_opt', field_type)
                fields.append(Field(
                    name=f['name'],
                    type_name=field_type,
                    optional=is_optional
                ))
            types[name] = StructType(name=name, fields=fields)
        elif type_name == 'Tuple':
            types[name] = TupleType(
                name=name,
                fields=defn.get('fields', [])
            )
        elif type_name == 'Union':
            variants = []
            tag = defn.get('tag')
            for v in defn.get('variants', []):
                if isinstance(v, str):
                    variants.append(Variant(name=v, type_name=None))
                else:
                    variants.append(Variant(
                        name=v['name'],
                        type_name=v.get('type', v['name'])
                    ))
            types[name] = UnionType(name=name, variants=variants, tag=tag)
        elif type_name == 'List':
            types[name] = ListType(
                name=name,
                values_type=defn.get('values', 'String'),
                max_size=defn.get('maxSize')
            )
        elif type_name == 'Map':
            values_optional = 'values_opt' in defn
            if values_optional:
                values_type = defn.get('values_opt', 'String')
            else:
                values_type = defn.get('values', 'String')
            types[name] = MapType(
                name=name,
                values_type=values_type,
                values_optional=values_optional
            )
        elif type_name == 'IMap':
            values_optional = 'values_opt' in defn
            if values_optional:
                values_type = defn.get('values_opt', 'String')
            else:
                values_type = defn.get('values', 'String')
            types[name] = IMapType(
                name=name,
                values_type=values_type,
                values_optional=values_optional
            )
        elif type_name == 'Bitfield':
            fields = []
            for f in defn.get('fields', []):
                bits_val = f.get('bits')
                if isinstance(bits_val, int):
                    bits = [bits_val]
                else:
                    bits = list(bits_val)
                fields.append(Field(
                    name=f['name'],
                    type_name=f.get('type', 'u32'),
                    bits=bits
                ))
            types[name] = BitfieldType(name=name, fields=fields)
        elif type_name == 'Enum':
            variants = []
            for v in defn.get('variants', []):
                if isinstance(v, str):
                    variants.append(Variant(name=v, type_name=None))
                else:
                    variants.append(Variant(
                        name=v['name'],
                        type_name=None,
                        value=v.get('value')
                    ))
            types[name] = EnumType(name=name, variants=variants)
        elif type_name == 'Error':
            variants = []
            for v in defn.get('variants', []):
                if isinstance(v, str):
                    variants.append(Variant(name=v, type_name=None))
                else:
                    variants.append(Variant(
                        name=v['name'],
                        type_name=None,
                        value=v.get('value')
                    ))
            types[name] = ErrorType(name=name, variants=variants)
        elif type_name == 'Extern':
            types[name] = ExternType(name=name)
        elif type_name == 'Int':
            types[name] = IntType(
                name=name,
                min=defn.get('min'),
                max=defn.get('max')
            )
        elif type_name == 'Double':
            types[name] = DoubleType(
                name=name,
                min=defn.get('min'),
                max=defn.get('max')
            )
        elif type_name == 'Decimal':
            types[name] = DecimalType(
                name=name,
                min=defn.get('min'),
                max=defn.get('max')
            )
        else:
            print(f"Warning: Unknown type '{type_name}' for {name}", file=sys.stderr)

    def parse_bool(val):
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ('true', '1', 'yes')
        return bool(val)

    methods = {}
    method_defs = data.get('methods', {})
    for method_name, defn in method_defs.items():
        methods[method_name] = Method(
            name=method_name,
            path_pattern=defn.get('path_pattern'),
            method_name=defn.get('name'),
            param=defn.get('param'),
            param_opt=defn.get('param_opt'),
            result=defn.get('result'),
            result_opt=defn.get('result_opt'),
            error=defn.get('error'),
            access=defn.get('access'),
            is_getter=parse_bool(defn.get('isGetter')),
            user_id_required=parse_bool(defn.get('userIdRequired')),
            signals=defn.get('signals'),
            description=defn.get('description'),
        )

    tree_data = data.get('tree', {})

    nodes_data = {}
    node_defs = data.get('nodes', {})
    for node_name, defn in node_defs.items():
        nodes_data[node_name] = NodeDef(
            name=node_name,
            methods=defn.get('methods', []),
            tree=defn.get('tree', {}),
        )

    return types, methods, tree_data, nodes_data

def parse_config(stream) -> tuple:
    data = yaml.load(stream, Loader=yaml.SafeLoader)
    components = data.get('components', [])
    newtype_list_map = data.get('newtype_list_map', False)
    return components, newtype_list_map

def resolve_ts_type(type_name: str, types: Dict[str, TypeDef]):
    if type_name in PRIMITIVE_TS:
        return PRIMITIVE_TS[type_name]

    if type_name in types:
        pascal = to_pascal_case(type_name)
        return f"{pascal}Zod"

    if type_name == 'DateTime':
        return 'z.date()'

    return 'z.any()'

def ts_string(value: str) -> str:
    escaped = value.replace('\\', '\\\\').replace("'", "\\'")
    return f"'{escaped}'"

def ts_object_key(value: str) -> str:
    if re.match(r'^[A-Za-z_$][A-Za-z0-9_$]*$', value):
        return value
    return ts_string(value)

def generate_types_code(types: Dict[str, TypeDef]) -> str:
    out: List[str] = []
    out.append("import * as z from 'libshv-js-zod';")
    out.append("import type {useShv} from 'vue-shv';")
    out.append("")

    def collect_deps(ty: TypeDef) -> List[str]:
        deps = set()
        def add_if_named(tn: Optional[str]):
            if not tn:
                return
            if tn in types:
                deps.add(tn)

        if isinstance(ty, StructType):
            for f in ty.fields:
                add_if_named(f.type_name)
        elif isinstance(ty, TupleType):
            for f in ty.fields:
                add_if_named(f)
        elif isinstance(ty, UnionType):
            for v in ty.variants:
                add_if_named(v.type_name)
        elif isinstance(ty, ListType):
            add_if_named(ty.values_type)
        elif isinstance(ty, MapType) or isinstance(ty, IMapType):
            add_if_named(ty.values_type)
        elif isinstance(ty, BitfieldType):
            for f in ty.fields:
                add_if_named(f.type_name)

        return list(deps)

    dep_graph: Dict[str, set] = {}
    for name, ty in types.items():
        dep_graph[name] = set(collect_deps(ty))

    order: List[str] = []
    no_deps = [n for n, d in dep_graph.items() if not d]
    while no_deps:
        n = no_deps.pop()
        order.append(n)

        for m in list(dep_graph.keys()):
            if n in dep_graph[m]:
                dep_graph[m].remove(n)
                if not dep_graph[m]:
                    no_deps.append(m)

    remaining = {n: d for n, d in dep_graph.items() if d}
    if remaining:
        cycles = ', '.join(f"{n} -> {','.join(sorted(list(d)))}" for n, d in remaining.items())
        raise RuntimeError(f"Type dependency cycle detected among types: {cycles}")

    for name in order:
        ty = types[name]
        pascal = to_pascal_case(name)

        if isinstance(ty, StructType):
            out.append(f"const {pascal}Zod = z.map({{")
            for f in ty.fields:
                field_name = ts_object_key(struct_wire_key(f.name))
                zod_expr = resolve_ts_type(f.type_name, types)
                if f.optional:
                    zod_expr = f"{zod_expr}.exactOptional()"
                out.append(f"    {field_name}: {zod_expr},")
            out.append("});")
            out.append(f"export type {pascal} = z.infer<typeof {pascal}Zod>;")
            out.append("")
        elif isinstance(ty, TupleType):
            z_elems = []
            for f in ty.fields:
                zod_expr = resolve_ts_type(f, types)
                z_elems.append(zod_expr)

            out.append(f"const {pascal}Zod = z.tuple([{', '.join(z_elems)}]);")
            out.append(f"export type {pascal} = z.infer<typeof {pascal}Zod>;")
            out.append("")
        elif isinstance(ty, ListType):
            val_zod = resolve_ts_type(ty.values_type, types)
            schema = f"z.array({val_zod})"
            if ty.max_size is not None:
                schema += f".max({ty.max_size})"
            out.append(f"const {pascal}Zod = {schema};")
            out.append(f"export type {pascal} = z.infer<typeof {pascal}Zod>;")
            out.append("")
        elif isinstance(ty, MapType):
            val_zod = resolve_ts_type(ty.values_type, types)
            if ty.values_optional:
                val_zod = f"{val_zod}.or(z.undefined())"
            out.append(f"const {pascal}Zod = z.recmap({val_zod});")
            out.append(f"export type {pascal} = z.infer<typeof {pascal}Zod>;")
            out.append("")
        elif isinstance(ty, IMapType):
            val_zod = resolve_ts_type(ty.values_type, types)
            if ty.values_optional:
                val_zod = f"{val_zod}.or(z.undefined())"

            out.append(f"const {pascal}Zod = z.recimap({val_zod});")
            out.append(f"export type {pascal} = z.infer<typeof {pascal}Zod>;")
            out.append("")
        elif isinstance(ty, BitfieldType):
            # FIXME: Improve bitfield support
            out.append(f"const {pascal}Zod = z.number();")
            out.append(f"export type {pascal} = z.infer<typeof {pascal}Zod>;")
            out.append("")
        elif isinstance(ty, UnionType):
            if ty.tag:
                variant_schemas = []
                for v in ty.variants:
                    if v.type_name:
                        inner_z = resolve_ts_type(v.type_name, types)
                        variant_schemas.append(f"z.object({{{ty.tag}: z.literal('{v.name}'), value: {inner_z}}})")
                    else:
                        variant_schemas.append(f"z.object({{{ty.tag}: z.literal('{v.name}')}})")
                out.append(f"const {pascal}Zod = z.discriminatedUnion('{ty.tag}', [")
                for variant_schema in variant_schemas:
                    out.append(f"    {variant_schema},")
                out.append("]).and(z.map({}));")
                out.append(f"export type {pascal} = z.infer<typeof {pascal}Zod>;")
                out.append("")
            else:
                if all(v.type_name is None for v in ty.variants):
                    out.append(f"export enum {pascal} {{")
                    for v in ty.variants:
                        out.append(f"    {to_pascal_case(v.name)} = '{v.name}',")
                    out.append("}")
                    out.append(f"const {pascal}Zod = z.enum({pascal});")
                    out.append("")
                    continue
                variant_schemas = []
                for v in ty.variants:
                    variant_key = ts_object_key(v.name)
                    if v.type_name:
                        inner_z = resolve_ts_type(v.type_name, types)
                        variant_schemas.append(f"z.object({{{variant_key}: {inner_z}}}).and(z.map({{}}))")
                    else:
                        variant_schemas.append(f"z.literal('{v.name}')")
                out.append(f"const {pascal}Zod = z.union([")
                for variant_schema in variant_schemas:
                    out.append(f"    {variant_schema},")
                out.append("]);")
                out.append(f"export type {pascal} = z.infer<typeof {pascal}Zod>;")
                out.append("")
        elif isinstance(ty, EnumType):
            out.append(f"export enum {pascal} {{")
            for v in ty.variants:
                if v.value is not None:
                    out.append(f"    {to_pascal_case(v.name)} = {v.value},")
                else:
                    out.append(f"    {to_pascal_case(v.name)},")
            out.append("}")
            out.append(f"const {pascal}Zod = z.enum({pascal});")
            out.append(f"export type {pascal}Type = z.infer<typeof {pascal}Zod>;")
            out.append("")
        elif isinstance(ty, ErrorType):
            # FIXME: Improve support for this
            literals = []
            for v in ty.variants:
                literals.append(f"z.literal('{v.name}')")
            out.append(f"const {pascal}Zod = z.union([{', '.join(literals)}]);")
            out.append(f"export type {pascal} = z.infer<typeof {pascal}Zod>;")
            out.append("")
        elif isinstance(ty, ExternType):
            # FIXME: Improve support for this
            out.append(f"const {pascal}Zod = z.any();")
            out.append(f"export type {pascal} = z.infer<typeof {pascal}Zod>;")
            out.append("")
        elif isinstance(ty, IntType):
            schema = "z.number()"
            if ty.min is not None:
                schema += f".min({ty.min})"
            if ty.max is not None:
                schema += f".max({ty.max})"
            out.append(f"const {pascal}Zod = {schema};")
            out.append(f"export type {pascal} = z.infer<typeof {pascal}Zod>;")
            out.append("")
        elif isinstance(ty, DoubleType):
            schema = "z.double()"
            if ty.min is not None:
                schema += f".min({ty.min})"
            if ty.max is not None:
                schema += f".max({ty.max})"
            out.append(f"const {pascal}Zod = {schema};")
            out.append(f"export type {pascal} = z.infer<typeof {pascal}Zod>;")
            out.append("")
        elif isinstance(ty, DecimalType):
            schema = "z.decimal()"
            if ty.min is not None:
                schema += f".min({ty.min})"
            if ty.max is not None:
                schema += f".max({ty.max})"
            out.append(f"const {pascal}Zod = {schema};")
            out.append(f"export type {pascal} = z.infer<typeof {pascal}Zod>;")
            out.append("")
        else:
            out.append(f"// Unknown type shape for {pascal}")
            out.append(f"const {pascal}Zod = z.any();")
            out.append(f"export type {pascal} = z.infer<typeof {pascal}Zod>;")
            out.append("")

    code = "\n".join(out)

    return code

def generate_methods_code(
    methods: Dict[str, Method],
    types: Dict[str, TypeDef],
    tree_data: Dict[str, str],
    nodes_data: Dict[str, NodeDef],
) -> str:
    if not methods:
        return ""

    def join_path(base: str, rel: str) -> str:
        base_norm = base.strip('/')
        rel_norm = rel.strip('/')
        if base_norm and rel_norm:
            return f"{base_norm}/{rel_norm}"
        if base_norm:
            return base_norm
        if rel_norm:
            return rel_norm
        return ""

    def method_rpc_name(method: Method) -> str:
        if method.method_name is None or method.method_name == '':
            raise RuntimeError(f"Method '{method.name}' is missing required 'name'")
        return method.method_name

    def make_call_expr(method: Method, node_path: str) -> str:
        func_name = method_rpc_name(method)
        path_expr = f"makeApiPath({ts_string(node_path)})"
        if method.param:
            param_schema = f"{to_pascal_case(method.param)}Zod" if method.param in types else resolve_ts_type(method.param, types)
            call_expr = f"makeRpcCallParam({path_expr}, {ts_string(func_name)}, {param_schema}, "
        elif method.param_opt:
            param_schema = f"{to_pascal_case(method.param_opt)}Zod" if method.param_opt in types else resolve_ts_type(method.param_opt, types)
            call_expr = f"makeRpcCallParam({path_expr}, {ts_string(func_name)}, {param_schema}.or(z.undefined()), "
        else:
            call_expr = f"makeRpcCall({path_expr}, {ts_string(func_name)}, "

        if method.result:
            result_schema = f"{to_pascal_case(method.result)}Zod" if method.result in types else resolve_ts_type(method.result, types)
            call_expr += result_schema + ")"
        elif method.result_opt:
            result_schema = f"{to_pascal_case(method.result_opt)}Zod" if method.result_opt in types else resolve_ts_type(method.result_opt, types)
            call_expr += f"{result_schema}.or(z.undefined()))"
        else:
            call_expr += "z.undefined())"

        return call_expr

    def emit_method_props(method_list: List[Method], child_keys: set[str], node_path: str, indent: str, out_lines: List[str]) -> None:
        seen_keys: Dict[str, str] = {}
        for method in method_list:
            key = method_rpc_name(method)
            emitted_key = key
            if key in child_keys:
                emitted_key = f"meth_{key}"

            if emitted_key in seen_keys:
                prev = seen_keys[emitted_key]
                raise RuntimeError(
                    f"Duplicate method name '{emitted_key}' at path '{node_path}' for methods '{prev}' and '{method.name}'"
                )

            if emitted_key in child_keys:
                raise RuntimeError(
                    f"Method name '{key}' at path '{node_path}' collides with child node '{emitted_key}'"
                )
            seen_keys[emitted_key] = method.name

        for method in method_list:
            key = method_rpc_name(method)
            emitted_key = key
            if key in child_keys:
                emitted_key = f"meth_{key}"
            out_lines.append(f"{indent}{ts_object_key(emitted_key)}: {make_call_expr(method, node_path)},")

    if not tree_data:
        return ""

    all_paths: Dict[str, str] = {}

    def add_path(path: str, node_type: str) -> None:
        if path not in all_paths:
            all_paths[path] = node_type

    def expand_node(node_type: str, path_prefix: str, active_node_types: Optional[List[str]] = None) -> None:
        if active_node_types is None:
            active_node_types = []
        if node_type in active_node_types:
            cycle = ' -> '.join(active_node_types + [node_type])
            raise RuntimeError(f"Node tree cycle detected: {cycle}")

        node = nodes_data.get(node_type)
        if node is None or not node.tree:
            return

        next_active_node_types = active_node_types + [node_type]
        for rel_path, child_type in node.tree.items():
            child_path = join_path(path_prefix, rel_path)
            if child_path == '':
                raise RuntimeError("Root tree paths are not supported")
            add_path(child_path, child_type)
            expand_node(child_type, child_path, next_active_node_types)

    for path, node_type in tree_data.items():
        normalized = path.strip('/')
        if normalized == '':
            raise RuntimeError("Root tree paths are not supported")
        add_path(normalized, node_type)
        expand_node(node_type, normalized)

    methods_by_path: Dict[str, List[Method]] = {}

    def add_method_for_path(path: str, method: Method) -> None:
        if path not in methods_by_path:
            methods_by_path[path] = []
        methods_by_path[path].append(method)

    for node_path, node_type in all_paths.items():
        node_def = nodes_data.get(node_type)
        if node_def is None or not node_def.methods:
            continue
        for method_name in node_def.methods:
            method = methods.get(method_name)
            if method is None:
                raise RuntimeError(
                    f"Node '{node_type}' at path '{node_path}' references unknown method '{method_name}'"
                )
            add_method_for_path(node_path, method)

    tree: Dict[str, Dict] = {}
    paths_for_tree = set(all_paths.keys()) | set(methods_by_path.keys())
    for full_path in paths_for_tree:
        if full_path == '':
            continue
        segments = full_path.split('/')
        cursor = tree
        for segment in segments:
            if segment not in cursor:
                cursor[segment] = {}
            cursor = cursor[segment]

    out = []
    out.append("export function createApi(")
    out.append("    getBasePath: () => string | Promise<string>,")
    out.append("    shv: Pick<ReturnType<typeof useShv>, 'makeRpcCall' | 'makeRpcCallParam'>,")
    out.append(") {")
    out.append("    const {makeRpcCall, makeRpcCallParam} = shv;")
    out.append(r"""    const normalizePath = (value: string) => {
        let start = 0;
        let end = value.length;

        while (start < end && value[start] === '/') {
            start += 1;
        }

        while (end > start && value[end - 1] === '/') {
            end -= 1;
        }

        return value.slice(start, end);
    };

    const makeApiPath = async (path: string) => {
        const basePath = await getBasePath();
        const baseNormalized = normalizePath(basePath);
        if (baseNormalized === '') {
            throw new Error('createApi: base path must not be empty');
        }

        const pathNormalized = normalizePath(path);

        if (pathNormalized === '') {
            throw new Error('createApi: node path must not be empty');
        }

        return `${baseNormalized}/${pathNormalized}`;
    };""")
    out.append("")
    out.append("    const api = {")

    def emit_entries(subtree: Dict[str, Dict], path_prefix: str, depth: int) -> None:
        indent = '    ' * depth
        path_methods = methods_by_path.get(path_prefix)
        if path_methods is not None:
            emit_method_props(path_methods, set(subtree.keys()), path_prefix, indent, out)

        for key in sorted(subtree.keys()):
            child_path = join_path(path_prefix, key)
            out.append(f"{indent}{ts_object_key(key)}: {{")
            emit_entries(subtree[key], child_path, depth + 1)
            out.append(f"{indent}}},")

    emit_entries(tree, '', 2)
    out.append("    } as const;")
    out.append("")
    out.append("    return api;")
    out.append("}")
    return "\n".join(out)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SHV IDL to TypeScript (Zod) code generator')
    parser.add_argument('--config', type=argparse.FileType('r'), required=True, help='YAML config file path')
    args = parser.parse_args()

    types, methods, tree_data, nodes_data = parse_yaml(sys.stdin)
    components, _newtype_list_map = parse_config(args.config)

    invalid_components = [component for component in components if component != 'client']
    if invalid_components:
        raise SystemExit(f"Unsupported TS generator components: {', '.join(invalid_components)}")

    generate_client = 'client' in components

    ts_types = generate_types_code(types)
    ts_methods = generate_methods_code(methods, types, tree_data, nodes_data) if generate_client else ""

    ts_types = ts_types.rstrip('\n')
    if ts_methods:
        ts_methods = ts_methods.lstrip('\n')
        final = ts_types + '\n\n' + ts_methods
    else:
        final = ts_types
    print(final)
