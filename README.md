# SHV IDL — Interface Definition Language for SHV RPC

SHV IDL is a YAML-based format for defining data types, RPC methods, and device tree structures for the [Silicon Heaven](https://github.com/svkh/silicon-heaven) protocol. The format is language-agnostic — language-specific generators produce native code from the same IDL. The **Rust generator** in [`generator-rust/`](./generator-rust/) produces type definitions (with serde), client call functions, server static node dispatchers, dynamic meta-method constants, and tree definitions.

---

## Table of Contents

- [IDL File Structure](#idl-file-structure)
  - [types](#types)
  - [methods](#methods)
  - [tree](#tree)
  - [nodes](#nodes)
- [Type System](#type-system)
  - [Primitives](#primitives)
  - [Struct](#struct)
  - [Tuple](#tuple)
  - [Union](#union)
  - [List](#list)
  - [Map](#map)
  - [Enum](#enum)
  - [Bitfield](#bitfield)
  - [Error](#error)
  - [Extern](#extern)
  - [Int](#int)
  - [Double](#double)
  - [Decimal](#decimal)
- [Method Definition](#method-definition)
- [Tree & Node System](#tree--node-system)
- [Generators](#generators)
- [Rust](#rust)
  - [Config File](#config-file)
  - [Generation Targets](#generation-targets)
  - [Usage](#usage)
- [TypeScript](#typescript)
  - [Config File](#config-file-1)
  - [Generation Targets](#generation-targets-1)
  - [Usage](#usage-1)
- [Schema Generation](#schema-generation)

---

## IDL File Structure

A complete IDL file has up to four top-level keys:

```yaml
types:    # (required) type definitions
methods:  # RPC method definitions
tree:     # flattened path-to-type mappings
nodes:    # named node definitions (methods + subtree)
```

## Type System

### Primitives

| IDL Type   | Rust Type            | TypeScript Type | Notes                         |
|------------|----------------------|-----------------|-------------------------------|
| `Null`     | `()`                 | `undefined`     | Unit type                     |
| `Bool`     | `bool`               | `boolean`       |                               |
| `Int`      | `i64`                | `number`        | 64-bit signed integer         |
| `Double`   | `f64`                | `Double`        | 64-bit floating point         |
| `Decimal`  | `shvproto::Decimal`  | `Decimal`       | Arbitrary precision decimal   |
| `String`   | `String`             | `string`        | UTF-8 string                  |
| `DateTime` | `shvproto::DateTime` | `Date`          | Unix timestamp (milliseconds) |
| `Blob`     | `Vec<u8>`            | `Blob`          | Binary data                   |

### Struct

Named fields with optional support. Two equivalent forms for optional fields:

```yaml
MyStruct:
  type: Struct
  fields:
    - name: requiredField
      type: String
    - name: optionalField
      type_opt: Int          # optional — uses `type_opt`
    - name: anotherOptional
      type: String
      optional: true         # optional — uses `optional` flag
```

### Tuple

Ordered fields without names. Use Tuple when the serialized shape is positional and field order carries meaning:

```yaml
GeoCoordinate:
  type: Tuple
  fields:
    - Double
    - Double

TimedCoordinate:
  type: Tuple
  fields:
    - DateTime
    - GeoCoordinate
```

Generates a named Rust tuple struct, for example `pub struct GeoCoordinate(pub f64, pub f64)`.

### Union

Discriminated union. **Externally tagged** by default (the variant name is the tag). **Internally tagged** when `tag` is specified (the discriminator is an inline field):

```yaml
# Externally tagged (default)
Response:
  type: Union
  variants:
    - name: Success
      type: ResultData
    - name: Error
      type: ErrorInfo
    - name: Pending                     # unit variant, no payload

# Internally tagged
Command:
  type: Union
  tag: cmd                              # adds a `type`-like discriminator field
  variants:
    - name: Start
      type: StartParams
    - name: Stop
      type: StopParams
```

Variants can also be shorthand strings (equivalent to unit variants):

```yaml
  variants:
    - Red
    - Green
    - Blue
```

### List

Homogeneous array with an optional `maxSize` constraint:

```yaml
SampleBuffer:
  type: List
  values: Double
  maxSize: 4096
```

By default generates `type SampleBuffer = Vec<f64>`. With `newtype_list_map: true` in config, generates a newtype struct.

### Map

Dictionary with string keys (always `String`). Values can be required or optional:

```yaml
# Required values
Attributes:
  type: Map
  values: String

# Optional values
Metadata:
  type: Map
  values_opt: String           # values are Option<String>
```

### IMap

Dictionary with integer keys (`i32` in Rust). Same value patterns as Map:

```yaml
# Required values
IndexedValues:
  type: IMap
  values: String

# Optional values
OptionalIndexed:
  type: IMap
  values_opt: String           # values are Option<String>
```

Generates `BTreeMap<i32, T>` in Rust.

### Enum

Integer-based enumeration. Variants can have explicit values or be auto-numbered (starting from 0):

```yaml
# Explicit values
State:
  type: Enum
  variants:
    - value: 0
      name: Off
    - value: 1
      name: On
    - value: 2
      name: Standby

# Auto-numbered
Color:
  type: Enum
  variants:
    - Red        # = 0
    - Green      # = 1
    - Blue       # = 2
```

### Bitfield

Bit-level field layout over a `u32`. Fields reference bit ranges or single bits. Can reference enum types for multi-bit fields:

```yaml
StatusRegister:
  type: Bitfield
  fields:
    - bits: [0, 1]       # 2-bit range (bits 0-1)
      type: OperatingMode
      name: mode
    - bits: 2             # single bit
      name: errorFlag
    - bits: [3, 5]        # 3-bit range
      type: AlertLevel
      name: alert
    - bits: 6
      name: busy
```

### Error

Named error variants for RPC error responses. Generates a Rust enum that maps to SHV user error codes:

```yaml
ApiError:
  type: Error
  variants:
    - name: NotFound
      value: 1
    - name: NotReachable
    - name: Timeout
```

### Extern

Placeholder for a type whose definition lives outside the IDL (in Rust code). The generator emits a `use` import for it:

```yaml
CustomType:
  type: Extern
```

### Int

Newtype wrapper around `i64` with optional `min`/`max` constraints. Generates a struct with `TryFrom<i64>` and `From<RpcValue>` conversions:

```yaml
Percentage:
  type: Int
  min: 0
  max: 100

SignalStrength:
  type: Int
  min: 0
```

### Double

Newtype wrapper around `f64` with optional `min`/`max` constraints — same pattern as Int:

```yaml
Temperature:
  type: Double
  min: -273.15

Voltage:
  type: Double
  min: 0
  max: 1000
```

### Decimal

Newtype wrapper around `shvproto::Decimal` with optional `min`/`max`
constraints — same pattern as Int/Double, but validates via `.to_f64()`:

```yaml
PreciseValue:
  type: Decimal
  min: 0
  max: 999999.99
```

Generates a struct with `TryFrom<Decimal>`, `TryFrom<&RpcValue>`, and `From`
conversions, plus `#[serde(try_from = "...", into = "...")]`.

## Method Definition

```yaml
methods:
  GetValue:
    name: get                       # RPC method name string
    path_pattern: "sensors/{id}"   # path template with {param} placeholders
    param: String                   # parameter type
    result: Measurement             # return type (defaults to Null)
    error: DeviceError              # optional error type
    access: rd                      # access level (see table below)
    isGetter: true                  # IsGetter flag
    userIdRequired: false           # UserIDRequired flag
    signals:                        # signal definitions
      chng: null                    # signal_name: param_type (null = no param)
    description: "Returns a measurement."
```

Use `result_opt` instead of `result` when the method may return `Null` — the generator wraps the type in an `Option`. The two keys are mutually exclusive:

```yaml
  GetOptional:
    name: get
    result_opt: Measurement         # returns Option<Measurement>
    access: rd
    isGetter: true
```

Use `param_opt` instead of `param` when the method accepts `Null` as a parameter — the generator wraps the type in an `Option`. The two keys are mutually exclusive:

```yaml
  SetOptional:
    name: set
    param_opt: Configuration        # accepts Option<Configuration>
    result: Null
    access: wr
```

### Access Levels

| Key   | Rust Enum Variant |
|-------|-------------------|
| `bws` | `Browse`          |
| `rd`  | `Read`            |
| `wr`  | `Write`           |
| `cmd` | `Command`         |
| `cfg` | `Config`          |
| `srv` | `Service`         |
| `ssrv`| `SuperService`    |
| `dev` | `Developer`       |
| `su`  | `Superuser`       |

## Tree & Node System

The **tree** maps flattened SHV paths to node type names:

```yaml
tree:
  device: RootDevice
  device/sensors/temperature: SensorNode
  device/config: ConfigNode
```

The **nodes** section defines each referenced node's methods and subtree:

```yaml
nodes:
  RootDevice:
    methods:
      - GetValue
      - Reboot
    tree:
      sensors/temperature: SensorNode
      config: ConfigNode

  SensorNode:
    methods:
      - GetMeasurement

  ConfigNode:
    methods:
      - GetConfig
      - SetConfig
```

## Generators

Each language has its own generator in a `generator-<lang>/` directory:

| Directory                           | Language | Status |
|-------------------------------------|----------|--------|
| [`generator-rust/`](./generator-rust/) | Rust     | Active |
| [`generator-ts/`](./generator-ts/)     | TypeScript | Active |

To add a new language, create a `generator-<lang>/` directory with a generator that reads the IDL YAML (the same schema as `example.yaml`) and emits the target language.

### Rust

#### Config File

A separate YAML config file controls code generation for the Rust generator:

```yaml
components:
  - client              # generate client call functions
  - server-static       # generate impl_static_node! macros
  - server-dynamic      # generate metamethods module
  - server-gate         # generate metamethods + tree_definition()

imports_module: "crate::imports"  # base path for Rust imports
newtype_list_map: false           # wrap List/Map in newtypes (vs type aliases)
```

#### Generation Targets

| Component        | Output                                                                 |
|-----------------|------------------------------------------------------------------------|
| `client`        | Async call functions per method, tree module with call helpers         |
| `server-static` | `impl_static_node!` macros for static method dispatch                  |
| `server-dynamic`| `metamethods` module with `MetaMethod` constants                       |
| `server-gate`   | Same as server-dynamic + `tree_definition()` returning `ShvTreeDefinition` |

---

#### Usage

```bash
# Pipe the IDL YAML with a config file to the Rust generator
cat my_definition.yaml | python3 generator-rust/shv_idl_generate_rust.py --config generator-rust/test_config.yaml > output.rs
```

See [`example.yaml`](./example.yaml) for a complete worked example covering every construct.

### TypeScript

#### Config File

A separate YAML config file controls code generation for the TypeScript generator:

```yaml
components:
  - client                # generate createApi() RPC helpers
```

#### Generation Targets

| Component | Output |
|-----------|--------|
| `client`  | Zod schemas + exported TS types + `createApi()` nested RPC helpers |

---

#### Usage

```bash
# Pipe the IDL YAML with a config file to the TypeScript generator
cat my_definition.yaml | python3 generator-ts/shv_idl_generate_typescript.py --config my_ts_config.yaml > api.ts
```

## Schema Generation

To auto-generate a JSON Schema from the Pydantic validator:

```bash
python3 -c "
import sys, json
sys.path.insert(0, '.')
from shv_idl_validate import SHVSchema
schema = SHVSchema.model_json_schema()
print(json.dumps(schema, indent=2))
"
```

This produces a complete structural schema covering all 12 type variants, methods, and nodes. Note that Pydantic's `model_validator` constraints (XOR on `type`/`type_opt` and `values`/`values_opt`) and cross-reference checks are not representable in JSON Schema and are omitted.
