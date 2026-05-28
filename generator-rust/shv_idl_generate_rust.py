#!/usr/bin/env python3
"""SHV IDL Parser - Generate Rust code from SHV IDL YAML definition"""

import argparse
import sys
import yaml
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, TextIO


PRIMITIVE_TYPES = {
    'Null': '()',
    'Int': 'i64',
    'Double': 'f64',
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
    value: Optional[int] = None


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
    imports_module = data.get('imports_module', 'crate')
    newtype_list_map = data.get('newtype_list_map', False)
    return components, imports_module, newtype_list_map


def resolve_type(type_name: str, types: Dict[str, TypeDef], imports_module: str = 'crate') -> str:
    if type_name in PRIMITIVE_TYPES:
        return PRIMITIVE_TYPES[type_name]

    if type_name in types:
        return to_pascal_case(type_name)

    if type_name == 'Int':
        return 'i64'
    if type_name == 'Double':
        return 'f64'
    if type_name == 'Decimal':
        return f"{imports_module}::shvproto::Decimal"
    if type_name == 'DateTime':
        return f"{imports_module}::shvproto::DateTime"

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


def generate_methods_code(methods: Dict[str, Method], types: Dict[str, TypeDef], generate_client: bool = True, imports_module: str = 'crate') -> str:
    if not methods:
        return ""

    output = []

    if generate_client:
        output.append(f"use {imports_module}::shvclient::clientapi::{{ClientCommandSender, RpcCall}};")
        output.append(f"use {imports_module}::shvrpc::join_path;")

    error_types = set()
    result_types = set()

    for m in methods.values():
        if m.error:
            error_types.add(m.error)
        if m.result:
            result_types.add(m.result)
        if m.result_opt:
            result_types.add(m.result_opt)

    if result_types:
        output.append(f"use {imports_module}::shvproto::RpcValue;")
    if error_types:
        output.append(f"use {imports_module}::shvclient::clientapi::{{RpcError, CallRpcMethodError, CallRpcMethodErrorKind}};")
        output.append(f"use {imports_module}::shvrpc::rpcmessage::{{RpcErrorCodeKind, USER_ERROR_CODE_DEFAULT}};")

    output.append("")
    output.append("// ============ Result type conversions ============")
    output.append("")

    for type_name in result_types:
        ty = types.get(type_name)
        if isinstance(ty, (StructType, EnumType, UnionType, BitfieldType)):
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
                if v.value is not None:
                    output.append(f"    {v_name} = USER_ERROR_CODE_DEFAULT + {v.value},")
                elif i == 0:
                    output.append(f"    {v_name} = USER_ERROR_CODE_DEFAULT + {i},")
                else:
                    output.append(f"    {v_name},")
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
            output.append("        let RpcErrorCodeKind::UserError(code) = value.code else {")
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


    if generate_client:
        output.append("// ============ Client API call functions ============")
        output.append("")

        for method in methods.values():
            method_name_snake = to_snake_case(method.name)
            method_name = method.method_name or method.name.lower()
            path_params = []
            if method.path_pattern:
                path_params = extract_path_params(method.path_pattern)

            if method.result_opt:
                inner = resolve_type(method.result_opt, types, imports_module)
                result_type = f"Option<{inner}>"
            elif method.result:
                result_type = resolve_type(method.result, types, imports_module)
            else:
                result_type = "()"
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
                param_type = resolve_type(method.param, types, imports_module)
                output.append(f"    param: {param_type},")
            elif method.param_opt:
                param_type = resolve_type(method.param_opt, types, imports_module)
                output.append(f"    param: Option<{param_type}>,")
            output.append("    client_tx: &ClientCommandSender,")
            output.append(f") -> Result<{result_type}, {error_type_with_generic}>")
            output.append("{")
            if method.path_pattern:
                path_format = method.path_pattern
                for p in path_params:
                    path_format = path_format.replace(f"{{{p}}}", f"{{{p}}}")
                output.append(f"    let path = join_path!(path_prefix, format!(\"{path_format}\"));")
            else:
                output.append("    let path = path_prefix.to_string();")
            output.append(f"    let rpc_call = RpcCall::new(&path, \"{method_name}\");")
            if method.param:
                output.append("    let rpc_call = rpc_call.param(param);")
            elif method.param_opt:
                output.append("    let rpc_call = if let Some(val) = param {")
                output.append("        rpc_call.param(val)")
                output.append("    } else {")
                output.append("        rpc_call")
                output.append("    };")
            output.append("    rpc_call.exec(client_tx)")
            output.append("        .await")
            if error_type:
                output.append("        .map_err(RpcCallError::from)")
            output.append("}")
            output.append("")

    return "\n".join(output)


ACCESS_MAP = {
    "bws": "Browse",
    "rd": "Read",
    "wr": "Write",
    "cmd": "Command",
    "cfg": "Config",
    "srv": "Service",
    "ssrv": "SuperService",
    "dev": "Developer",
    "su": "Superuser",
}


def generate_static_node_code(nodes_data: Dict[str, NodeDef], methods: Dict[str, Method], types: Dict[str, TypeDef], imports_module: str = 'crate') -> str:
    nodes_with_methods = {name: n for name, n in nodes_data.items() if n.methods}
    if not nodes_with_methods:
        return ""

    output = []

    for node_name, node in nodes_with_methods.items():
        pascal_name = to_pascal_case(node_name)
        output.append(f"use {imports_module}::nodes::{pascal_name};")
        output.append(f"{imports_module}::shvclient::impl_static_node! {{")
        output.append(f"    {pascal_name}(&self, request, client_cmd_tx) {{")

        for method_name in node.methods:
            method = methods.get(method_name)
            if not method:
                continue

            method_str = method.method_name or "get"

            flags = []
            if method.is_getter:
                flags.append("IsGetter")
            if method.user_id_required:
                flags.append("UserIDRequired")
            flags_str = " | ".join(flags) if flags else "None"

            access_str = ACCESS_MAP.get(method.access, "Read")

            param_type = method.param or method.param_opt or "Null"

            param_str = ""
            args_str = "request, client_cmd_tx"
            if method.param:
                param_str = f' (param: {resolve_type(param_type, types, imports_module)})'
                args_str = "request, param, client_cmd_tx"
            elif method.param_opt:
                param_str = f' (param: Option<{resolve_type(param_type, types, imports_module)}>)'
                args_str = "request, param, client_cmd_tx"

            if method.result:
                result_type = method.result
                if method.error:
                    result_type = f"{result_type}|{to_pascal_case(method.error)}"
            elif method.result_opt:
                result_type = method.result_opt
                if method.error:
                    result_type = f"{result_type}|Null|{to_pascal_case(method.error)}"
            else:
                result_type = "Null"

            signals_str = ""
            if method.signals:
                signal_items = []
                for sig_name, sig_val in method.signals.items():
                    if sig_val is None:
                        signal_items.append(f'("{sig_name}", None)')
                    else:
                        signal_items.append(f'("{sig_name}", Some("{sig_val}"))')
                signals_str = " { " + ", ".join(signal_items) + " }"

            snake_name = to_snake_case(method_name)

            param_type = method.param if method.param else (f"{method.param_opt}|Null" if method.param_opt else "Null")

            output.append(f'        "{method_str}" [{flags_str}, {access_str}, "{param_type}", "{result_type}"]{param_str}{signals_str} => {{')
            output.append(f"            self.{snake_name}({args_str}).await")
            output.append("        }")
            output.append("")

        output.append("    }")
        output.append("}")
        output.append("")

    return "\n".join(output)


def generate_metamethods_code(methods: Dict[str, Method], imports_module: str = 'crate') -> str:
    methods_with_access = {name: m for name, m in methods.items() if m.access}
    if not methods_with_access:
        return ""

    output = []
    output.append("pub mod metamethods {")
    output.append(f"    use {imports_module}::shvrpc::metamethod::{{MetaMethod, Flags, AccessLevel}};")
    output.append("")

    for method_name, method in methods_with_access.items():
        const_name = f"META_METHOD_{to_snake_case(method.name).upper()}"

        method_name_str = method.method_name or "get"

        flags_parts = []
        if method.is_getter:
            flags_parts.append("Flags::IsGetter")
        if method.user_id_required:
            flags_parts.append("Flags::UserIDRequired")

        if len(flags_parts) == 1:
            flags_str = f"{flags_parts[0]}"
        elif len(flags_parts) > 1:
            flags_str = "Flags::None.union(" + ".union(".join(flags_parts) + ")" * len(flags_parts)
        else:
            flags_str = "Flags::None"

        access_str = f'AccessLevel::{ACCESS_MAP.get(method.access, "Read")}'

        param_type = method.param if method.param else (f"{method.param_opt}|Null" if method.param_opt else "Null")

        if method.result:
            result_type = method.result
            if method.error:
                result_type = f"{result_type}|{to_pascal_case(method.error)}"
        elif method.result_opt:
            result_type = method.result_opt
            if method.error:
                result_type = f"{result_type}|Null|{to_pascal_case(method.error)}"
        else:
            result_type = "Null"

        if method.signals:
            signal_items = []
            for sig_name, sig_val in method.signals.items():
                if sig_val is None:
                    signal_items.append(f'("{sig_name}", None)')
                else:
                    signal_items.append(f'("{sig_name}", Some("{sig_val}"))')
            signals_str = f"&[{', '.join(signal_items)}]"
        else:
            signals_str = "&[]"

        description = method.description or ""

        output.append(f"    pub const {const_name}: MetaMethod = MetaMethod::new_static(")
        output.append(f'        "{method_name_str}",')
        output.append(f"        {flags_str},")
        output.append(f"        {access_str},")
        output.append(f'        "{param_type}",')
        output.append(f'        "{result_type}",')
        output.append(f"        {signals_str},")
        output.append(f'        "{description}"')
        output.append("    );")
        output.append("")

    output.append("}")
    return "\n".join(output)


def generate_tree_code(tree_data: Dict[str, str], nodes_data: Dict[str, NodeDef], methods: Dict[str, Method], types: Dict[str, TypeDef], generate_client: bool = True, generate_tree_definition: bool = True, imports_module: str = 'crate') -> str:
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

    clientapi_path = f"{imports_module}::shvclient::clientapi"
    shvrpc_path = f"{imports_module}::shvrpc"

    output = []
    output.append("pub mod tree {")

    def emit_method(method_name: str, depth: int) -> None:
        method = methods.get(method_name)
        if not method:
            return
        func_name = method.method_name
        if method.result_opt:
            inner = resolve_type(method.result_opt, types, imports_module)
            result_type = f"Option<{inner}>"
        elif method.result:
            result_type = resolve_type(method.result, types, imports_module)
        else:
            result_type = '()'
        param_type = resolve_type(method.param, types, imports_module) if method.param else None
        param_opt_type = resolve_type(method.param_opt, types, imports_module) if method.param_opt else None
        output.append(f"{'    ' * (depth)}use {imports_module}::api::*;")
        error_type = "CallRpcMethodError"
        if method.error and method.error in types and isinstance(types[method.error], ErrorType):
            error_type = f"RpcCallError<{to_pascal_case(method.error)}>"
        sig = f"{'    ' * depth}pub async fn {func_name}(mount_path: &str, "
        if param_type:
            sig += f"param: {param_type}, "
        if param_opt_type:
            sig += f"param: Option<{param_opt_type}>, "
        sig += f"client_tx: &{clientapi_path}::ClientCommandSender) -> Result<{result_type}, {error_type}> {{"
        output.append(sig)
        if method.param_opt:
            output.append(f"{'    ' * (depth+1)}let rpc_call = {clientapi_path}::RpcCall::new({shvrpc_path}::join_path!(mount_path, NODE_PATH), \"{func_name}\");")
            output.append(f"{'    ' * (depth+1)}let rpc_call = if let Some(val) = param {{")
            output.append(f"{'    ' * (depth+1)}    rpc_call.param(val)")
            output.append(f"{'    ' * (depth+1)}}} else {{")
            output.append(f"{'    ' * (depth+1)}    rpc_call")
            output.append(f"{'    ' * (depth+1)}}};")
            output.append(f"{'    ' * (depth+1)}rpc_call.exec(client_tx)")
            output.append(f"{'    ' * (depth+1)}    .await")
        else:
            output.append(f"{'    ' * (depth+1)}{clientapi_path}::RpcCall::new({shvrpc_path}::join_path!(mount_path, NODE_PATH), \"{func_name}\")")
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
                output.append(f"{'    ' * (depth+1)}pub const NODE_PATH: &str = \"{full_path}\";")
                if generate_client:
                    for mn in node_def.methods:
                        emit_method(mn, depth + 1)
            if isinstance(val, dict):
                render_module(val, full_path, depth + 1)
            output.append(f"{'    ' * depth}}}")

    render_module(tree, "", 1)
    output.append("}")

    if generate_tree_definition:
        paths_with_methods = {}
        for path, type_name in all_paths.items():
            node_def = nodes_data.get(type_name)
            if node_def and node_def.methods:
                paths_with_methods[path] = node_def.methods

        if paths_with_methods:
            output.append("")
            output.append(f"pub fn tree_definition() -> shvgate::ShvTreeDefinition {{")
            output.append("    let mut nodes_description = std::collections::BTreeMap::new();")
            output.append("")

            for path in sorted(paths_with_methods.keys()):
                meta_methods = ", ".join(f"metamethods::META_METHOD_{to_snake_case(m).upper()}" for m in paths_with_methods[path])
                path_modules = "::".join(sanitize_module_name(s) for s in path.split('/'))
                output.append(f'    nodes_description.insert(tree::{path_modules}::NODE_PATH.clone(), NodeDescription {{ methods: vec![{meta_methods}] }});')

            output.append("")
            output.append(f"    shvgate::ShvTreeDefinition {{ nodes_description }}")
            output.append("}")

    return "\n".join(output)


def generate_rust_code(types: Dict[str, TypeDef], methods: Dict[str, Method] = None, newtype_list_map: bool = False, imports_module: str = 'crate', tree_data: Dict[str, str] = None, nodes_data: Dict[str, NodeDef] = None, generate_client: bool = True, generate_static_tree: bool = True, generate_metamethods: bool = True, generate_shvgate_tree: bool = False) -> str:
    structs = []
    bitfields = []
    enums = []
    lists = []
    maps = []
    unions = []
    externs = []
    ints = []
    doubles = []
    decimals = []

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
        elif isinstance(t, IntType):
            ints.append(t)
        elif isinstance(t, DoubleType):
            doubles.append(t)
        elif isinstance(t, DecimalType):
            decimals.append(t)

    output = []
    output.append("use serde::{Serialize, Deserialize};")

    if bitfields:
        output.append("use bitfield_struct::bitfield;")
    if enums:
        output.append("use bitfield_struct::bitenum;")
    if maps:
        output.append("use std::collections::BTreeMap;")
    if decimals:
        output.append(f"use {imports_module}::shvproto::RpcValue;")

    output.append("")
    output.append("// ============ External types imports ============")
    for t in externs:
        output.append(f'use {imports_module}::{t.name}')
    output.append("")

    output.append("// ============ Structs ============")
    output.append("")

    for s in structs:
        output.append("#[derive(Debug, Clone, Serialize, Deserialize)]")
        output.append('#[serde(rename_all = "camelCase")]')
        struct_name = to_pascal_case(s.name)
        output.append(f"pub struct {struct_name} {{")
        for f in s.fields:
            rust_type = resolve_type(f.type_name, types, imports_module)
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
        output.append("#[derive(Clone, Serialize, Deserialize)]")
        output.append('#[serde(from = "u32", into = "u32")]')
        bf_name = to_pascal_case(bf.name)
        output.append(f"pub struct {bf_name} {{")

        layout = generate_bitfield_layout(bf.fields)

        for field_name, field_type, start, size in layout:
            if field_name == '_':
                dummy_name = f"_:_"
                output.append(f"    #[bits({size})] {dummy_name},")
            else:
                resolved_type = resolve_type(field_type, types, imports_module)
                output.append(f"    #[bits({size})] pub {to_snake_case(field_name)}: {resolved_type},")

        output.append("}")
        output.append("")

    output.append("// ============ Lists ============")
    output.append("")

    for lst in lists:
        val_type = resolve_type(lst.values_type, types, imports_module)
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
        key_type = resolve_type(mp.keys_type, types, imports_module)
        val_type = resolve_type(mp.values_type, types, imports_module)
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
                resolved = resolve_type(v.type_name, types, imports_module)
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
            if v.value is not None:
                output.append(f"    {v_name} = {v.value},")
            else:
                output.append(f"    {v_name},")
        output.append("}")
        output.append("")

    output.append("// ============ Newtype Ints ============")
    output.append("")

    for t in ints:
        name = to_pascal_case(t.name)
        impl_min = t.min if t.min is not None else "i64::MIN"
        impl_max = t.max if t.max is not None else "i64::MAX"

        output.append("#[derive(Debug, Clone, Serialize, Deserialize)]")
        output.append('#[serde(try_from = "i64", into = "i64")]')
        output.append(f"pub struct {name}(i64);")
        output.append("")
        output.append(f"impl {name} {{")
        output.append(f"    pub fn value(&self) -> i64 {{ self.0 }}")
        output.append(f"}}")
        output.append("")
        output.append(f"impl TryFrom<i64> for {name} {{")
        output.append("    type Error = String;")
        output.append("")
        output.append(f"    fn try_from(value: i64) -> Result<Self, Self::Error> {{")
        output.append(f"        const MIN_VALUE: i64 = {impl_min};")
        output.append(f"        const MAX_VALUE: i64 = {impl_max};")
        output.append("        if value < MIN_VALUE || value > MAX_VALUE {")
        output.append("            return Err(format!(\"Value `{value}` out of range, must be within [{MIN_VALUE}, {MAX_VALUE}]\"));")
        output.append("        }")
        output.append("        Ok(Self(value))")
        output.append("    }")
        output.append("}")
        output.append("")
        output.append(f"impl TryFrom<&RpcValue> for {name} {{")
        output.append("    type Error = String;")
        output.append("")
        output.append("    fn try_from(value: &RpcValue) -> Result<Self, Self::Error> {")
        output.append("        let v: i64 = value.try_into()?;")
        output.append("        v.try_into()")
        output.append("    }")
        output.append("}")
        output.append("")
        output.append(f"impl From<{name}> for i64 {{")
        output.append(f"    fn from(value: {name}) -> Self {{")
        output.append("        value.0")
        output.append("    }")
        output.append("}")
        output.append("")
        output.append(f"impl From<{name}> for RpcValue {{")
        output.append(f"    fn from(value: {name}) -> Self {{")
        output.append("        value.0.into()")
        output.append("    }")
        output.append("}")
        output.append("")

    output.append("// ============ Newtype Doubles ============")
    output.append("")

    for t in doubles:
        name = to_pascal_case(t.name)
        impl_min = t.min if t.min is not None else "f64::MIN"
        impl_max = t.max if t.max is not None else "f64::MAX"

        output.append("#[derive(Debug, Clone, Serialize, Deserialize)]")
        output.append('#[serde(try_from = "f64", into = "f64")]')
        output.append(f"pub struct {name}(f64);")
        output.append("")
        output.append(f"impl {name} {{")
        output.append(f"    pub fn value(&self) -> f64 {{ self.0 }}")
        output.append(f"}}")
        output.append("")
        output.append(f"impl TryFrom<f64> for {name} {{")
        output.append("    type Error = String;")
        output.append("")
        output.append(f"    fn try_from(value: f64) -> Result<Self, Self::Error> {{")
        output.append(f"        const MIN_VALUE: f64 = {impl_min};")
        output.append(f"        const MAX_VALUE: f64 = {impl_max};")
        output.append("        if value < MIN_VALUE || value > MAX_VALUE {")
        output.append("            return Err(format!(\"Value `{value}` out of range, must be within [{MIN_VALUE}, {MAX_VALUE}]\"));")
        output.append("        }")
        output.append("        Ok(Self(value))")
        output.append("    }")
        output.append("}")
        output.append("")
        output.append(f"impl TryFrom<&RpcValue> for {name} {{")
        output.append("    type Error = String;")
        output.append("")
        output.append("    fn try_from(value: &RpcValue) -> Result<Self, Self::Error> {")
        output.append("        let v: f64 = value.try_into()?;")
        output.append("        v.try_into()")
        output.append("    }")
        output.append("}")
        output.append("")
        output.append(f"impl From<{name}> for f64 {{")
        output.append(f"    fn from(value: {name}) -> Self {{")
        output.append("        value.0")
        output.append("    }")
        output.append("}")
        output.append("")
        output.append(f"impl From<{name}> for RpcValue {{")
        output.append(f"    fn from(value: {name}) -> Self {{")
        output.append("        value.0.into()")
        output.append("    }")
        output.append("}")
        output.append("")

    output.append("// ============ Newtype Decimals ============")
    output.append("")

    for t in decimals:
        name = to_pascal_case(t.name)
        decimal_type = f"{imports_module}::shvproto::Decimal"
        impl_min = t.min if t.min is not None else "f64::MIN"
        impl_max = t.max if t.max is not None else "f64::MAX"

        output.append("#[derive(Debug, Clone, Serialize, Deserialize)]")
        output.append(f'#[serde(try_from = "{decimal_type}", into = "{decimal_type}")]')
        output.append(f"pub struct {name}({decimal_type});")
        output.append("")
        output.append(f"impl {name} {{")
        output.append(f"    pub fn value(&self) -> {decimal_type} {{ self.0 }}")
        output.append(f"}}")
        output.append("")
        output.append(f"impl TryFrom<{decimal_type}> for {name} {{")
        output.append("    type Error = String;")
        output.append("")
        output.append(f"    fn try_from(value: {decimal_type}) -> Result<Self, Self::Error> {{")
        output.append("        let v = value.to_f64();")
        output.append(f"        const MIN_VALUE: f64 = {impl_min};")
        output.append(f"        const MAX_VALUE: f64 = {impl_max};")
        output.append("        if v < MIN_VALUE || v > MAX_VALUE {")
        output.append("            return Err(format!(\"Value `{v}` out of range, must be within [{MIN_VALUE}, {MAX_VALUE}]\"));")
        output.append("        }")
        output.append("        Ok(Self(value))")
        output.append("    }")
        output.append("}")
        output.append("")
        output.append(f"impl TryFrom<&RpcValue> for {name} {{")
        output.append("    type Error = String;")
        output.append("")
        output.append("    fn try_from(value: &RpcValue) -> Result<Self, Self::Error> {")
        output.append(f"        let v: {decimal_type} = value.try_into()?;")
        output.append("        v.try_into()")
        output.append("    }")
        output.append("}")
        output.append("")
        output.append(f"impl From<{name}> for {decimal_type} {{")
        output.append(f"    fn from(value: {name}) -> Self {{")
        output.append("        value.0")
        output.append("    }")
        output.append("}")
        output.append("")
        output.append(f"impl From<{name}> for RpcValue {{")
        output.append(f"    fn from(value: {name}) -> Self {{")
        output.append("        value.0.into()")
        output.append("    }")
        output.append("}")
        output.append("")

    if methods:
        methods_code = generate_methods_code(methods, types, generate_client, imports_module)
        if methods_code:
            output.append("")
            output.append(methods_code)

    if methods and generate_metamethods:
        metamethods_code = generate_metamethods_code(methods, imports_module)
        if metamethods_code:
            output.append("")
            output.append(metamethods_code)

    if tree_data or nodes_data:
        tree_code = generate_tree_code(tree_data or {}, nodes_data or {}, methods or {}, types, generate_client, generate_shvgate_tree, imports_module)
        if tree_code:
            output.append("")
            output.append(tree_code)

    if nodes_data and generate_static_tree:
        static_node_code = generate_static_node_code(nodes_data, methods or {}, types, imports_module)
        if static_node_code:
            output.append("")
            output.append(static_node_code)

    return "\n".join(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SHV IDL to Rust code generator')
    parser.add_argument('--config', type=argparse.FileType('r'), required=True, help='YAML config file path')
    args = parser.parse_args()

    types, methods, tree_data, nodes_data = parse_yaml(sys.stdin)

    components, imports_module, newtype_list_map = parse_config(args.config)

    generate_client = 'client' in components
    generate_static_tree = 'server-static' in components
    generate_metamethods = 'server-dynamic' in components or 'server-gate' in components
    generate_shvgate_tree = 'server-gate' in components

    if not components:
        generate_client = generate_static_tree = generate_dynamic = generate_gate = False

    code = generate_rust_code(
        types, methods,
        newtype_list_map=newtype_list_map,
        imports_module=imports_module,
        tree_data=tree_data,
        nodes_data=nodes_data,
        generate_client=generate_client,
        generate_static_tree=generate_static_tree,
        generate_metamethods=generate_metamethods,
        generate_shvgate_tree=generate_shvgate_tree,
    )
    print(code)
