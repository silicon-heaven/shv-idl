#!/usr/bin/env python3

import sys
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


AccessLevel = Literal["bws", "rd", "wr", "cmd", "cfg", "srv", "ssrv", "dev", "su"]


class StructField(StrictModel):
    name: str
    type: Optional[str] = None
    type_opt: Optional[str] = None
    optional: Optional[bool] = None

    @model_validator(mode='after')
    def check_xor(self):
        if (self.type is None) == (self.type_opt is None):
            raise ValueError("Exactly one of 'type' or 'type_opt' must be provided")
        if self.optional is not None and self.type_opt is not None:
            raise ValueError("'optional' can only be combined with 'type', not 'type_opt'")
        return self

class UnionVariant(StrictModel):
    name: str
    type: Optional[str] = None

class BitfieldField(StrictModel):
    name: str
    type: Optional[str] = None
    bits: Union[int, List[int]]

class EnumVariant(StrictModel):
    name: str
    value: Optional[int] = Field(None, ge=0)

class Struct(StrictModel):
    type: Literal["Struct"]
    fields: List[StructField]

class TupleType(StrictModel):
    type: Literal["Tuple"]
    fields: List[str]

class UnionType(StrictModel):
    type: Literal["Union"]
    tag: Optional[str] = None
    variants: List[Union[str, UnionVariant]]

class ListType(StrictModel):
    type: Literal["List"]
    values: str
    maxSize: Optional[int] = Field(None, ge=1)

class MapType(StrictModel):
    type: Literal["Map"]
    values: Optional[str] = None
    values_opt: Optional[str] = None

    @model_validator(mode='after')
    def check_xor(self):
        if (self.values is None) == (self.values_opt is None):
            raise ValueError("Exactly one of 'values' or 'values_opt' must be provided")
        return self

class IMapType(StrictModel):
    type: Literal["IMap"]
    values: Optional[str] = None
    values_opt: Optional[str] = None

    @model_validator(mode='after')
    def check_xor(self):
        if (self.values is None) == (self.values_opt is None):
            raise ValueError("Exactly one of 'values' or 'values_opt' must be provided")
        return self

class Bitfield(StrictModel):
    type: Literal["Bitfield"]
    fields: List[BitfieldField]

class EnumType(StrictModel):
    type: Literal["Enum"]
    variants: List[Union[str, EnumVariant]]

class ErrorType(StrictModel):
    type: Literal["Error"]
    variants: List[Union[str, EnumVariant]]

class IntType(StrictModel):
    type: Literal["Int"]
    min: Optional[int] = None
    max: Optional[int] = None

class DoubleType(StrictModel):
    type: Literal["Double"]
    min: Optional[float] = None
    max: Optional[float] = None

class DecimalType(StrictModel):
    type: Literal["Decimal"]
    min: Optional[float] = None
    max: Optional[float] = None

class Extern(StrictModel):
    type: Literal["Extern"]
    import_rust: Optional[str] = None
    import_ts: Optional[str] = None

class Method(StrictModel):
    name: str
    path_pattern: Optional[str] = None
    param: Optional[str] = None
    param_opt: Optional[str] = None
    result: Optional[str] = None
    result_opt: Optional[str] = None
    error: Optional[str] = None
    access: Optional[AccessLevel] = None
    isGetter: Optional[bool] = None
    userIdRequired: Optional[bool] = None
    signals: Optional[Dict[str, Any]] = None
    description: Optional[str] = None

    @model_validator(mode='after')
    def check_result_xor(self):
        if self.result is not None and self.result_opt is not None:
            raise ValueError("'result' and 'result_opt' are mutually exclusive")
        return self

    @model_validator(mode='after')
    def check_param_xor(self):
        if self.param is not None and self.param_opt is not None:
            raise ValueError("'param' and 'param_opt' are mutually exclusive")
        return self

class NodeDef(StrictModel):
    methods: Optional[List[str]] = None
    tree: Optional[Dict[str, str]] = None

BasicType = Annotated[
    Union[Struct, TupleType, UnionType, ListType, MapType, IMapType, Bitfield, EnumType, ErrorType, IntType, DoubleType, DecimalType, Extern],
    Field(discriminator='type')
]

class SHVSchema(StrictModel):
    types: Dict[str, BasicType]
    methods: Dict[str, Method]
    tree: Dict[str, str]
    nodes: Dict[str, NodeDef]

    @model_validator(mode='after')
    def validate_cross_references(self) -> 'SHVSchema':
        basic_types = ['Null', 'Bool', 'Int', 'Double', 'Decimal', 'DateTime', 'String', 'Blob', 'List', 'Map', 'IMap', 'Bitfield', 'Enum']
        defined_types = list(self.types.keys())
        all_types = basic_types + defined_types
        enum_types = [k for k, v in self.types.items() if isinstance(v, EnumType)]

        for name, definition in self.types.items():
            if isinstance(definition, Struct):
                for f in definition.fields:
                    if f.type and f.type not in all_types:
                        raise ValueError(f"Struct '{name}' field '{f.name}' references unknown type '{f.type}'")
                    if f.type_opt and f.type_opt not in all_types:
                        raise ValueError(f"Struct '{name}' field '{f.name}' references unknown type '{f.type_opt}'")
            if isinstance(definition, TupleType):
                for f in definition.fields:
                    if f not in all_types:
                        raise ValueError(f"Tuple '{name}' field references unknown type '{f}'")
            if isinstance(definition, UnionType):
                for v in definition.variants:
                    if isinstance(v, str):
                        continue
                    elif isinstance(v, UnionVariant):
                        variant_type = v.type or v.name
                        if variant_type not in all_types:
                            raise ValueError(f"Union '{name}' variant '{v.name}' references unknown type '{variant_type}'")
            if isinstance(definition, MapType):
                if definition.values and definition.values not in all_types:
                    raise ValueError(f"Map '{name}' references unknown type '{definition.values}'")
                if definition.values_opt and definition.values_opt not in all_types:
                    raise ValueError(f"Map '{name}' references unknown type '{definition.values_opt}'")
            if isinstance(definition, IMapType):
                if definition.values and definition.values not in all_types:
                    raise ValueError(f"IMap '{name}' references unknown type '{definition.values}'")
                if definition.values_opt and definition.values_opt not in all_types:
                    raise ValueError(f"IMap '{name}' references unknown type '{definition.values_opt}'")
            if isinstance(definition, ListType):
                if definition.values not in all_types:
                    raise ValueError(f"List '{name}' references unknown type '{definition.values}'")
            if isinstance(definition, Bitfield):
                for f in definition.fields:
                    if f.type and f.type not in enum_types:
                        raise ValueError(f"Bitfield '{name}' field '{f.name}' must refer to an Enum. '{f.type}' is not an Enum.")

        if self.methods:
            for mname, method in self.methods.items():
                if method.param and method.param not in all_types:
                    raise ValueError(f"Method '{mname}' references unknown parameter type '{method.param}'")
                if method.param_opt and method.param_opt not in all_types:
                    raise ValueError(f"Method '{mname}' references unknown parameter type '{method.param_opt}'")
                if method.result and method.result not in all_types:
                    raise ValueError(f"Method '{mname}' references unknown result type '{method.result}'")
                if method.result_opt and method.result_opt not in all_types:
                    raise ValueError(f"Method '{mname}' references unknown result type '{method.result_opt}'")
                if method.error and method.error not in all_types:
                    raise ValueError(f"Method '{mname}' references unknown error type '{method.error}'")

        if self.nodes:
            for nname, node in self.nodes.items():
                if node.methods:
                    for mid in node.methods:
                        if mid not in self.methods:
                            raise ValueError(f"Node '{nname}' references unknown method '{mid}'")
                if node.tree:
                    for path, child in node.tree.items():
                        if child not in self.nodes:
                            raise ValueError(f"Node '{nname}' tree child '{path}' references unknown node '{child}'")

        for path, node_name in self.tree.items():
            if node_name not in self.nodes:
                raise ValueError(f"Tree entry '{path}' references unknown node '{node_name}'")

        return self

def main():
    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            print("Error: No input provided on stdin.")
            sys.exit(1)

        data = yaml.safe_load(raw_input)
        SHVSchema.model_validate(data)
        print("Validation Successful")
        sys.exit(0)

    except yaml.YAMLError as e:
        print(f"YAML Parsing Error: {e}")
        sys.exit(1)
    except ValidationError as e:
        print(f"Validation Failed:\n{e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
