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
class ExternType(TypeDef):
    import_str: Optional[str] = None


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


def parse_yaml(stream: TextIO) -> Dict[str, TypeDef]:
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
                    type_name=f.get('type', 'i64'),
                    bits=bits
                ))
            types[name] = BitfieldType(name=name, fields=fields)

        elif type_name == 'Enum':
            variants = []
            for v in defn.get('variants', []):
                variants.append(Variant(
                    name=v['name'],
                    type_name=None
                ))
            types[name] = EnumType(name=name, variants=variants)

        elif type_name == 'Extern':
            types[name] = ExternType(name=name, import_str=defn.get('import-rust'))

        else:
            print(f"Warning: Unknown type '{type_name}' for {name}", file=sys.stderr)

    return types


def resolve_type(type_name: str, types: Dict[str, TypeDef]) -> str:
    if type_name in PRIMITIVE_TYPES:
        return PRIMITIVE_TYPES[type_name]

    if type_name in types:
        return to_pascal_case(type_name)

    return type_name


def generate_bitfield_layout(fields: List[Field]) -> List[tuple]:
    layout = []
    current_bit = 0

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


def generate_rust_code(types: Dict[str, TypeDef], newtype_list_map: bool = False) -> str:
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

    for t in externs:
       output.append(f"{t.import_str}")

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
                output.append(f"    #[bits({size})] pub {field_name}: {resolved_type},")

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
        if newtype_list_map:
            output.append("#[derive(Debug, Clone, Serialize, Deserialize)]")
            output.append('#[serde(transparent)]')
            lst_name = to_pascal_case(lst.name)
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
        output.append(f"pub enum {e.name} {{")
        for i, v in enumerate(e.variants):
            v_name = to_pascal_case(v.name)
            if i == 0:
                output.append(f"    #[default] #[fallback]")
            output.append(f"    {v_name} = {i},")
        output.append("}")
        output.append("")

    return "\n".join(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SHV IDL to Rust code generator')
    parser.add_argument('--newtype', action='store_true', help='Generate List/Map as newtype structs instead of type aliases')
    args = parser.parse_args()

    types = parse_yaml(sys.stdin)
    code = generate_rust_code(types, newtype_list_map=args.newtype)
    print(code)
