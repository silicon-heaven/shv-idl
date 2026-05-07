#!/usr/bin/env python3

import sys
import yaml
from typing import Annotated, Dict, List, Optional, Union, Literal, Any
from pydantic import BaseModel, Field, model_validator, ValidationError

class StructField(BaseModel):
    name: str
    type: Optional[str] = None
    type_opt: Optional[str] = None

    @model_validator(mode='after')
    def check_xor(self):
        if (self.type is None) == (self.type_opt is None):
            raise ValueError("Exactly one of 'type' or 'type_opt' must be provided")
        return self

class UnionVariant(BaseModel):
    name: str
    type: Optional[str] = None

class BitfieldField(BaseModel):
    name: str
    type: Optional[str] = None
    bits: Union[int, List[int]]

class EnumVariant(BaseModel):
    name: str
    value: Optional[int] = Field(None, ge=0)

class Struct(BaseModel):
    type: Literal["Struct"]
    fields: List[StructField]

class UnionType(BaseModel):
    type: Literal["Union"]
    tag: Optional[str] = None
    variants: List[Union[str, UnionVariant]]

class ListType(BaseModel):
    type: Literal["List"]
    values: str
    maxSize: Optional[int] = Field(None, ge=1)

class MapType(BaseModel):
    type: Literal["Map"]
    keys: str
    values: Optional[str] = None
    values_opt: Optional[str] = None

    @model_validator(mode='after')
    def check_xor(self):
        if (self.values is None) == (self.values_opt is None):
            raise ValueError("Exactly one of 'values' or 'values_opt' must be provided")
        return self

class Bitfield(BaseModel):
    type: Literal["Bitfield"]
    fields: List[BitfieldField]

class EnumType(BaseModel):
    type: Literal["Enum"]
    variants: Optional[List[EnumVariant]] = None
    fields: Optional[List[EnumVariant]] = None

    @model_validator(mode='after')
    def check_xor(self):
        if (self.variants is None) == (self.fields is None):
            raise ValueError("Exactly one of 'variants' or 'fields' must be provided")
        return self

class Extern(BaseModel):
    type: Literal["Extern"]
    import_rust: Optional[str] = None
    import_ts: Optional[str] = None

BasicType = Annotated[
    Union[Struct, UnionType, ListType, MapType, Bitfield, EnumType, Extern],
    Field(discriminator='type')
]

class SHVSchema(BaseModel):
    types: Dict[str, BasicType]
    methods: Optional[Dict[str, Any]] = None

    @model_validator(mode='after')
    def validate_cross_references(self) -> 'SHVSchema':
        basic_types = ['Null', 'Bool', 'Int', 'Double', 'DateTime', 'String', 'Blob', 'List', 'Map', 'IMap', 'Bitfield', 'Enum']
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
            if isinstance(definition, UnionType):
                for v in definition.variants:
                    if isinstance(v, str):
                        if v not in all_types:
                            raise ValueError(f"Union '{name}' variant '{v}' references unknown type '{v}'")
                    elif isinstance(v, UnionVariant):
                        if v.type and v.type not in all_types:
                            raise ValueError(f"Union '{name}' variant '{v.name}' references unknown type '{v.type}'")
            if isinstance(definition, MapType):
                if definition.values and definition.values not in all_types:
                    raise ValueError(f"Map '{name}' references unknown type '{definition.values}'")
                if definition.values_opt and definition.values_opt not in all_types:
                    raise ValueError(f"Map '{name}' references unknown type '{definition.values_opt}'")
            if isinstance(definition, ListType):
                if definition.values not in all_types:
                    raise ValueError(f"List '{name}' references unknown type '{definition.values}'")
            if isinstance(definition, Bitfield):
                for f in definition.fields:
                    if f.type and f.type not in enum_types:
                        raise ValueError(f"Bitfield '{name}' field '{f.name}' must refer to an Enum. '{f.type}' is not an Enum.")
        return self

def main():
    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            print("Error: No input provided on stdin.")
            sys.exit(1)

        data = yaml.safe_load(raw_input)
        validated = SHVSchema.model_validate(data)
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
