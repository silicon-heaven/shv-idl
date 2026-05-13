#!/usr/bin/env python3
"""SHV IDL Parser - Generate Rust code from SHV IDL YAML definition"""

import argparse
import sys
import yaml
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, TextIO

yaml.add_constructor('tag:yaml.org,2002:bool', lambda loader, node: node.value, Loader=yaml.SafeLoader)

PRIMITIVE_TYPES = {
    'Null': '()',
    'Int': 'i64',
    'Double': 'f64',
    'DateTime': 'i64',
    'String': 'String',
    'Blob': 'Vec<u8>',
    'Bool': 'bool',
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


@dataclass
class TypeDef:
    name: str


@dataclass
class StructType(TypeDef):
    fields: List[Field] = field(default_factory=list)


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
    keys_type: str = 'String'
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
class Method:
    name: str
    path_pattern: Optional[str] = None
    method_name: Optional[str] = None
    param: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None


@dataclass
class NodeDef:
    name: str
    methods: List[str] = field(default_factory=list)
    tree: Dict[str, str] = field(default_factory=dict)


def to_pascal_case(name: str) -> str:
    # Split on:
    # - transitions from lower/digit -> upper
    # - non-alphanumeric separators
    parts = re.findall(
        r'[A-Z]+(?=[A-Z][a-z]|[0-9]|\b)|[A-Z]?[a-z]+|[0-9]+',
        name
    )
    return ''.join(part.capitalize() for part in parts)


def to_snake_case(name: str) -> str:
    # Replace non-alphanumeric separators with underscores
    name = re.sub(r'[^A-Za-z0-9]+', '_', name)
    # Split acronym-word boundaries: HTTPServer -> HTTP_Server
    name = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', name)
    # Split camelCase/PascalCase boundaries
    name = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name)
    # Normalize underscores
    return re.sub(r'_+', '_', name).strip('_').lower()


RUST_KEYWORDS = {
    'as', 'async', 'await', 'box', 'break', 'const', 'continue', 'crate', 'dyn',
    'else', 'enum', 'extern', 'false', 'fn', 'for', 'if', 'impl', 'in', 'let',
    'loop', 'match', 'mod', 'move', 'mut', 'pub', 'ref', 'return', 'self',
    'Self', 'static', 'struct', 'super', 'trait', 'true', 'type', 'unsafe', 'use',
    'where', 'while', 'union',
}


def sanitize_module_name(name: str) -> str:
    if name in RUST_KEYWORDS:
        return f'r#{name}'
    return name


def parse_yaml(stream: TextIO) -> tuple[Dict[str, TypeDef], Dict[str, Method], Dict[str, str], Dict[str, NodeDef]]:
    data = yaml.load(stream, Loader=yaml.SafeLoader)

    types = {}
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

        elif type_name == 'Union':
            variants = []
            tag = defn.get('tag')
            for v in defn.get('variants', []):
                if isinstance(v, str):
                    variants.append(Variant(name=v, type_name=v))
                else:
                    variants.append(Variant(
                        name=v['name'],
                        type_name=v.get('type')
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
                keys_type=defn.get('keys', 'String'),
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
                        type_name=None
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
                        type_name=None
                    ))
            types[name] = ErrorType(name=name, variants=variants)

        elif type_name == 'Extern':
            types[name] = ExternType(name=name)

        else:
            print(f"Warning: Unknown type '{type_name}' for {name}", file=sys.stderr)

    methods = {}
    method_defs = data.get('methods', {})
    for method_name, defn in method_defs.items():
        methods[method_name] = Method(
            name=method_name,
            path_pattern=defn.get('path_pattern'),
            method_name=defn.get('name'),
            param=defn.get('param'),
            result=defn.get('result'),
            error=defn.get('error'),
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


def resolve_type(type_name: str, types: Dict[str, TypeDef]) -> str:
    if type_name in PRIMITIVE_TYPES:
        return PRIMITIVE_TYPES[type_name]

    if type_name in types:
        return to_pascal_case(type_name)

    return type_name


def generate_bitfield_layout(fields: List[Field]) -> List[tuple]:
    layout = []
    current_bit = 0

    fields.sort(key=lambda f: min(f.bits))

    for f in fields:
        bits = f.bits
        if not bits:
            continue

        start = min(bits)
        end = max(bits) + 1
        size = end - start

        if current_bit < start:
            layout.append(('_', '_', current_bit, start - current_bit))

        layout.append((f.name, f.type_name, start, size))
        current_bit = end

    return layout


def extract_path_params(path_pattern: str) -> List[str]:
    import re
    pattern = r'\{([^}]+)\}'
    return re.findall(pattern, path_pattern)


def generate_methods_code(methods: Dict[str, Method], types: Dict[str, TypeDef]) -> str:
    if not methods:
        return ""

    output = []
    output.append("use libshvgate::shvclient::clientapi::{RpcCall, CallRpcMethodError, CallRpcMethodErrorKind};")

    error_types = set()
    result_types = set()

    for m in methods.values():
        if m.error:
            error_types.add(m.error)
        if m.result:
            result_types.add(m.result)

    output.append("")
    output.append("// ============ Result type conversions ============")
    output.append("")

    for type_name in result_types:
        ty = types.get(type_name)
        if isinstance(ty, StructType) or isinstance(ty, EnumType) or isinstance(ty, UnionType) or isinstance(ty, BitfieldType):
            resolved = to_pascal_case(type_name)
            output.append(f"impl TryFrom<&RpcValue> for {resolved} {{")
            output.append("    type Error = String;")
            output.append("")
            output.append("    fn try_from(value: &RpcValue) -> Result<Self, Self::Error> {")
            output.append("        shvproto::from_rpcvalue(value).map_err(|e| e.to_string())")
            output.append("    }")
            output.append("}")
            output.append("")

    output.append("// ============ Error type annotations ============")
    output.append("")

    for type_name in error_types:
        if type_name in types and isinstance(types[type_name], ErrorType):
            error_type = types[type_name]
            resolved = to_pascal_case(type_name)
            output.append(f"#[repr(u32)]")
            output.append(f"pub enum {resolved} {{")
            for i, v in enumerate(error_type.variants):
                v_name = to_pascal_case(v.name)
                output.append(f"    {v_name} = shvrpc::rpcmessage::USER_ERROR_CODE_DEFAULT + {i},")
            output.append("}")
            output.append("")

            output.append(f"impl From<{resolved}> for RpcError {{")
            output.append(f"    fn from(value: {resolved}) -> Self {{")
            output.append(f"        match value {{")
            for v in error_type.variants:
                v_name = to_pascal_case(v.name)
                output.append(f"            {resolved}::{v_name} => RpcError::new(value as u32, \"{v_name}\"),")
            output.append("        }")
            output.append("    }")
            output.append("}")
            output.append("")

            output.append(f"impl TryFrom<&RpcError> for {resolved} {{")
            output.append("    type Error = ();")
            output.append("")
            output.append("    fn try_from(value: &RpcError) -> Result<Self, Self::Error> {")
            output.append("        let shvrpc::rpcmessage::RpcErrorCodeKind::UserError(code) = value.code else {")
            output.append("            return Err(())")
            output.append("        };")
            output.append("        match code {")
            for v in error_type.variants:
                v_name = to_pascal_case(v.name)
                output.append(f"            _ if code == {resolved}::{v_name} as _ => Ok({resolved}::{v_name}),")
            output.append("            _ => Err(()),")
            output.append("        }")
            output.append("    }")
            output.append("}")
            output.append("")

    output.append("// ============ RpcCallError wrapper ============")
    output.append("")
    output.append("pub enum RpcCallError<T> {")
    output.append("    Specific(T),")
    output.append("    Generic(CallRpcMethodError),")
    output.append("}")
    output.append("")
    output.append("impl<T> From<CallRpcMethodError> for RpcCallError<T>")
    output.append("    where for<'a> T: TryFrom<&'a RpcError>")
    output.append("{")
    output.append("    fn from(value: CallRpcMethodError) -> Self {")
    output.append("        let CallRpcMethodErrorKind::RpcError(rpc_error) = value.error() else {")
    output.append("            return Self::Generic(value)")
    output.append("        };")
    output.append("        let Ok(specific_error) = T::try_from(rpc_error) else {")
    output.append("            return Self::Generic(value)")
    output.append("        };")
    output.append("        Self::Specific(specific_error)")
    output.append("    }")
    output.append("}")
    output.append("")

    output.append("// ============ Call functions ============")
    output.append("")

    for method in methods.values():
        method_name_snake = to_snake_case(method.name)
        method_name = method.method_name or method.name.lower()
        path_params = []
        if method.path_pattern:
            path_params = extract_path_params(method.path_pattern)

        result_type = resolve_type(method.result or 'Null', types) if method.result else "()"
        error_type = None
        if method.error and method.error in types and isinstance(types[method.error], ErrorType):
            error_type = to_pascal_case(method.error)
            error_type_with_generic = f"RpcCallError<{error_type}>"
        else:
            error_type_with_generic = "CallRpcMethodError"

        output.append(f"pub async fn call_{method_name_snake}(")
        output.append("    path_prefix: &str,")
        for p in path_params:
            output.append(f"    {p}: &str,")
        if method.param:
            param_type = resolve_type(method.param, types)
            output.append(f"    param: {param_type},")
        output.append("    client_tx: &ClientCommandSender,")
        output.append(f") -> Result<{result_type}, {error_type_with_generic}>")
        output.append("{")
        if method.path_pattern:
            path_format = method.path_pattern
            for p in path_params:
                path_format = path_format.replace(f"{{{p}}}", f"{{{p}}}")
            output.append(f"    let path = shvrpc::join_path!(path_prefix, format!(\"{path_format}\"));")
        else:
            output.append("    let path = path_prefix.to_string();")
        output.append(f"    let rpc_call = RpcCall::new(&path, \"{method_name}\");")
        if method.param:
            output.append("    let rpc_call = rpc_call.param(param);")
        output.append("    rpc_call.exec(client_tx)")
        output.append("        .await")
        if error_type:
            output.append("        .map_err(RpcCallError::from)")
        output.append("}")
        output.append("")

    output.append("// ============ Method handlers ============")
    output.append("")

    for method in methods.values():
        method_name_snake = to_snake_case(method.name)
        path_params = []
        if method.path_pattern:
            path_params = extract_path_params(method.path_pattern)

        result_type = resolve_type(method.result or 'Null', types) if method.result else "()"
        error_type = to_pascal_case(method.error) if method.error and method.error in types and isinstance(types[method.error], ErrorType) else "()"

        output.append(f"pub async fn method_handler_{method_name_snake}(")
        for p in path_params:
            output.append(f"    {p}: String,")
        if method.param:
            param_type = resolve_type(method.param, types)
            output.append(f"    param: {param_type},")
        output.append(f") -> Result<{result_type}, {error_type}> " + "{")
        output.append("    todo!()")
        output.append("}")
        output.append("")

    return "\n".join(output)


def generate_tree_code(tree_data: Dict[str, str], nodes_data: Dict[str, NodeDef], methods: Dict[str, Method], types: Dict[str, TypeDef]) -> str:
    if not tree_data:
        return ""

    all_paths = {}

    def add_path(path: str, type_name: str) -> None:
        if path not in all_paths:
            all_paths[path] = type_name

    def expand_node(type_name: str, path_prefix: str) -> None:
        node = nodes_data.get(type_name)
        if not node or not node.tree:
            return
        for rel_path, child_type in node.tree.items():
            child_path = f"{path_prefix}/{rel_path}"
            add_path(child_path, child_type)
            expand_node(child_type, child_path)

    for path, type_name in tree_data.items():
        add_path(path, type_name)
        node = nodes_data.get(type_name)
        if node and node.tree:
            expand_node(type_name, path)

    tree = {}

    def build_tree_from_path(path: str) -> None:
        segs = path.split('/')
        d = tree
        for seg in segs:
            if not isinstance(d.get(seg), dict):
                d[seg] = {}
            d = d[seg]

    for path in all_paths.keys():
        build_tree_from_path(path)

    output = []
    output.append("pub mod tree {")
    output.append("    use libshvgate::shvclient::clientapi::RpcCall;")

    def emit_method(method_name: str, depth: int) -> None:
        method = methods.get(method_name)
        if not method:
            return
        func_name = method.method_name
        result_type = resolve_type(method.result or 'Null', types) if method.result else '()'
        param_type = resolve_type(method.param, types) if method.param else None
        error_type = "CallRpcMethodError"
        if method.error and method.error in types and isinstance(types[method.error], ErrorType):
            error_type = f"RpcCallError<{to_pascal_case(method.error)}>"
        sig = f"{'    ' * depth}pub async fn {func_name}(mount_path: &str, "
        if param_type:
            sig += f"param: {param_type}, "
        sig += f"client_tx: &ClientCommandSender) -> Result<{result_type}, {error_type}> {{"
        output.append(sig)
        output.append(f"{'    ' * (depth+1)}RpcCall::new(shvrpc::join_path!(mount_path, _NODE_PATH), \"{func_name}\")")
        if param_type:
            output.append(f"{'    ' * (depth+1)}    .param(param)")
        output.append(f"{'    ' * (depth+1)}    .exec(client_tx)")
        output.append(f"{'    ' * (depth+1)}    .await")
        if error_type != "CallRpcMethodError":
            output.append(f"{'    ' * (depth+1)}    .map_err(RpcCallError::from)")
        output.append(f"{'    ' * depth}}}")

    def render_module(d: Dict, path_prefix: str, depth: int) -> None:
        for key in sorted(d.keys()):
            val = d[key]
            full_path = f"{path_prefix}/{key}" if path_prefix else key
            output.append(f"{'    ' * depth}pub mod {sanitize_module_name(key)} {{")
            node_def = nodes_data.get(all_paths.get(full_path))
            if node_def and node_def.methods:
                output.append(f"{'    ' * (depth+1)}const _NODE_PATH: &str = \"{full_path}\";")
                for mn in node_def.methods:
                    emit_method(mn, depth + 1)
            if isinstance(val, dict):
                render_module(val, full_path, depth + 1)
            output.append(f"{'    ' * depth}}}")

    render_module(tree, "", 1)
    output.append("}")
    return "\n".join(output)


def generate_rust_code(types: Dict[str, TypeDef], methods: Dict[str, Method] = None, newtype_list_map: bool = False, extern_imports: List[str] = None, tree_data: Dict[str, str] = None, nodes_data: Dict[str, NodeDef] = None) -> str:
    structs = []
    bitfields = []
    enums = []
    lists = []
    maps = []
    unions = []
    externs = []

    for name, t in types.items():
        if isinstance(t, StructType):
            structs.append(t)
        elif isinstance(t, BitfieldType):
            bitfields.append(t)
        elif isinstance(t, EnumType):
            enums.append(t)
        elif isinstance(t, ListType):
            lists.append(t)
        elif isinstance(t, MapType):
            maps.append(t)
        elif isinstance(t, UnionType):
            unions.append(t)
        elif isinstance(t, ExternType):
            externs.append(t)

    output = []
    output.append("use serde::{Serialize, Deserialize};")

    if bitfields:
        output.append("use bitfield_struct::bitfield;")
    if enums:
        output.append("use bitfield_struct::bitenum;")
    if maps:
        output.append("use std::collections::BTreeMap;")

    for import_str in (extern_imports or []):
        output.append(import_str)

    output.append("")

    output.append("// ============ Structs ============")
    output.append("")

    for s in structs:
        output.append("#[derive(Debug, Clone, Serialize, Deserialize)]")
        output.append('#[serde(rename_all = "camelCase")]')
        struct_name = to_pascal_case(s.name)
        output.append(f"pub struct {struct_name} {{")
        for f in s.fields:
            rust_type = resolve_type(f.type_name, types)
            field_name = to_snake_case(f.name)
            if f.optional:
                output.append(f"    pub {field_name}: Option<{rust_type}>,")
            else:
                output.append(f"    pub {field_name}: {rust_type},")
        output.append("}")
        output.append("")

    output.append("// ============ Bitfields ============")
    output.append("")

    for bf in bitfields:
        output.append(f"#[bitfield(u32)]")
        bf_name = to_pascal_case(bf.name)
        output.append(f"pub struct {bf_name} {{")

        layout = generate_bitfield_layout(bf.fields)

        for field_name, field_type, start, size in layout:
            if field_name == '_':
                dummy_name = f"_:_"
                output.append(f"    #[bits({size})] {dummy_name},")
            else:
                resolved_type = resolve_type(field_type, types)
                output.append(f"    #[bits({size})] pub {to_snake_case(field_name)}: {resolved_type},")

        output.append("}")
        output.append("")

        output.append(f"impl serde::Serialize for {bf_name} {{")
        output.append(f"    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>")
        output.append(f"        where S: serde::Serializer {{")
        output.append(f"            serializer.serialize_u32(self.into_bits())")
        output.append(f"    }}")
        output.append(f"}}")
        output.append("")

        output.append(f"impl<'de> serde::Deserialize<'de> for {bf_name} {{")
        output.append(f"    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>")
        output.append(f"        where D: serde::Deserializer<'de> {{")
        output.append(f"            let bits = serde::de::Value::deserialize(deserializer)?;")
        output.append(f"            Ok(Self::from_bits(bits))")
        output.append(f"    }}")
        output.append(f"}}")
        output.append("")

    output.append("// ============ Lists ============")
    output.append("")

    for lst in lists:
        val_type = resolve_type(lst.values_type, types)
        lst_name = to_pascal_case(lst.name)
        if newtype_list_map:
            output.append("#[derive(Debug, Clone, Serialize, Deserialize)]")
            output.append('#[serde(transparent)]')
            output.append(f"pub struct {lst_name}(pub Vec<{val_type}>);")
        else:
            output.append(f"pub type {lst_name} = Vec<{val_type}>;")
        output.append("")

    output.append("// ============ Maps ============")
    output.append("")

    for mp in maps:
        key_type = resolve_type(mp.keys_type, types)
        val_type = resolve_type(mp.values_type, types)
        mp_name = to_pascal_case(mp.name)
        if mp.values_optional:
            val_type = f"Option<{val_type}>"
        if newtype_list_map:
            output.append("#[derive(Debug, Clone, Serialize, Deserialize)]")
            output.append('#[serde(transparent)]')
            output.append(f"pub struct {mp_name}(pub BTreeMap<{key_type}, {val_type}>);")
        else:
            output.append(f"pub type {mp_name} = BTreeMap<{key_type}, {val_type}>;")
        output.append("")

    output.append("// ============ Unions ============")
    output.append("")

    for u in unions:
        output.append(f"#[derive(Debug, Clone, Serialize, Deserialize)]")
        u_name = to_pascal_case(u.name)
        output.append(f"pub enum {u_name} {{")
        for v in u.variants:
            v_name = to_pascal_case(v.name)
            if v.type_name:
                resolved = resolve_type(v.type_name, types)
                output.append(f"    {v_name}({resolved}),")
            else:
                output.append(f"    {v_name},")
        output.append("}")
        output.append("")

    output.append("// ============ Enums ============")
    output.append("")

    for e in enums:
        output.append("#[bitenum]")
        output.append("#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]")
        output.append("#[repr(u32)]")
        e_name = to_pascal_case(e.name)
        output.append(f"pub enum {e_name} {{")
        for i, v in enumerate(e.variants):
            v_name = to_pascal_case(v.name)
            if i == 0:
                output.append(f"    #[default] #[fallback]")
            output.append(f"    {v_name} = {i},")
        output.append("}")
        output.append("")

    if methods:
        methods_code = generate_methods_code(methods, types)
        if methods_code:
            output.append("")
            output.append(methods_code)

    if tree_data or nodes_data:
        tree_code = generate_tree_code(tree_data or {}, nodes_data or {}, methods or {}, types)
        if tree_code:
            output.append("")
            output.append(tree_code)

    return "\n".join(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SHV IDL to Rust code generator')
    parser.add_argument('--newtype', action='store_true', help='Generate List/Map as newtype structs instead of type aliases')
    parser.add_argument('--extern-import', action='append', dest='extern_imports', default=[],
                        metavar='IMPORT_STR', help='Import string for an Extern type (repeatable)')
    parser.add_argument('--tree', action='store_true', help='Generate tree/nodes module code')
    args = parser.parse_args()

    types, methods, tree_data, nodes_data = parse_yaml(sys.stdin)
    code = generate_rust_code(
        types, methods,
        newtype_list_map=args.newtype,
        extern_imports=args.extern_imports,
        tree_data=tree_data if args.tree else None,
        nodes_data=nodes_data if args.tree else None,
    )
    print(code)
