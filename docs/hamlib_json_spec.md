# Hamlib JSON Specification

This document defines the JSON representation of Hamlib commands. This specification is derived from the `multirig/hamlib/messages.py` Pydantic models.

## Base Structure

All commands share a common set of fields:

```json
{
  "cmd": "string",
  "erp_prefix": "string | null",
  "request_id": "string | null",
  "source": "string | null",
  "raw_command": "string | null"
}
```

- **`cmd`**: The command identifier (e.g., "F", "m", "dump_state"). Matches the `HamlibProtocol` enum.
- **`erp_prefix`**: Keep-alive prefix for Extended Response Protocol (e.g., "+"). Null if standard protocol.
- **`request_id`**: Optional unique identifier for tracking requests.
- **`source`**: Optional identifier for the source of the command (e.g., "tcp", "web").
- **`raw_command`**: The original raw command string, including arguments.

## Commands

### Rigs Control

#### Set Frequency (`F`)
Sets the frequency of the rig.
```json
{
  "cmd": "F",
  "frequency": 14074000
}
```

#### Get Frequency (`f`)
Requests the current frequency.
```json
{
  "cmd": "f"
}
```

#### Set Mode (`M`)
Sets the mode and optional passband.
```json
{
  "cmd": "M",
  "mode": "USB",
  "passband": 2400
}
```

#### Get Mode (`m`)
Requests current mode and passband.
```json
{
  "cmd": "m"
}
```

#### Set VFO (`V`)
Sets the current VFO.
```json
{
  "cmd": "V",
  "vfo": "VFOA"
}
```

#### Get VFO (`v`)
Requests current VFO.
```json
{
  "cmd": "v"
}
```

#### Check VFO (`chk_vfo`)
Special command for checking VFO status.
```json
{
  "cmd": "chk_vfo",
  "is_raw": false
}
```
*   `is_raw`: If true, indicates the command was sent with a backslash prefix (e.g. `\chk_vfo`).

### PTT Control

#### Set PTT (`T`)
Sets Push-To-Talk status.
```json
{
  "cmd": "T",
  "ptt": 1
}
```
*   `ptt`: 1 for ON (TX), 0 for OFF (RX).

#### Get PTT (`t`)
Requests current PTT status.
```json
{
  "cmd": "t"
}
```

### State & Capabilities

#### Dump State (`dump_state`)
Requests a full dump of rig state.
```json
{
  "cmd": "dump_state"
}
```

#### Dump Capabilities (`dump_caps`)
Requests rig capabilities structure.
```json
{
  "cmd": "dump_caps"
}
```

#### Get Power Status (`get_powerstat`)
Requests power status (On/Off/Standby).
```json
{
  "cmd": "get_powerstat"
}
```

#### Get Split VFO (`s` / `get_split_vfo`)
Requests split mode status.
```json
{
  "cmd": "get_split_vfo"
}
```

### Configuration & Info

#### Get Info (`get_info`)
Requests general rig information string.
```json
{
  "cmd": "get_info"
}
```

#### Get Level (`l`)
Requests a specific level value (e.g., RF Power, Mic Gain).
```json
{
  "cmd": "l",
  "level_name": "RFPOWER"
}
```

#### Set Config (`set_conf`)
Sets a token-based configuration parameter.
```json
{
  "cmd": "set_conf",
  "token": "dtr",
  "value": "1"
}
```

#### Get Config (`get_conf`)
Gets a token-based configuration parameter.
```json
{
  "cmd": "get_conf",
  "token": "dtr"
}
```

## Responses

Responses are JSON objects corresponding to the command issued. All responses include a `cmd` field referencing the original command, and a `result` field.

### Base Response Structure
```json
{
  "cmd": "string",
  "request_id": "string | null",
  "source": "string | null",
  "destination": "string | null",
  "raw_response": "string | null",
  "result": 0
}
```
- **`cmd`**: The command identifier matching the request (e.g. "f", "M").
- **`request_id`**: The ID from the original request.
- **`source`**: The source from the original request.
- **`destination`**: The destination (matches request source).
- **`raw_response`**: The full raw string returned by rigctld.
- **`result`**: The integer result code (RPRT code). `0` indicates success. Negative values indicate errors (e.g. `-11` for Feature Not Available).

### Success Response
Returned by `Set` commands (e.g. `F`, `M`, `V`, `T`) and generic acknowledgements.
```json
{
  "cmd": "F",
  "result": 0
}
```

### Data Responses

#### Frequency Response (`f`)
```json
{
  "cmd": "f",
  "result": 0,
  "frequency": 14074000
}
```

#### Mode Response (`m`)
```json
{
  "cmd": "m",
  "result": 0,
  "mode": "USB",
  "passband": 2400
}
```

#### VFO Response (`v`)
```json
{
  "cmd": "v",
  "result": 0,
  "vfo": "VFOA"
}
```

#### PTT Response (`t`)
```json
{
  "cmd": "t",
  "result": 0,
  "ptt": 1
}
```
* `ptt`: 1 (TX) or 0 (RX).

#### Chunked Responses (`dump_state`, `dump_caps`)
For large dumps, the response contains a list of raw lines.

**`dump_state` Output Example**:
```json
{
  "cmd": "dump_state",
  "data_lines": [
    "1",                                     // Model ID
    "1",                                     // Connection Status
    "150000.000000 1500000000.000000 ...",   // Frequency Ranges
    "0 0 0 0 0 0 0",                        // Rit/Xit/etc
    "...",
    "rig_model=1",                           // Key-Value pairs at end
    "rigctld_version=Hamlib 4.6.5 ..."
  ],
  "result": 0
}
```

**`dump_caps` Output Example**:
```json
{
  "cmd": "dump_caps",
  "data_lines": [
    "Model Name", "Dummy",
    "Model ID", "1",
    "Can set Frequency", "Y",
    "...",
    "Frequency Ranges",
    "100000 30000000 0x1",
    "End Frequency Ranges",
    "..."
  ],
  "result": 0
}
```
* Note: The `lines` array contains the raw string output split by newlines. Parsing these lines requires knowledge of the specific Hamlib version and rig driver.
