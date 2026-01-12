# rigctld TCP Protocol (Hamlib) — Implementation Guide

This document describes how to implement a TCP client for Hamlib’s `rigctld` daemon (“rigctl over TCP”). It is intended to be implementation-oriented (framing, parsing, error handling, and common commands).

Authoritative references:

- `ext/hamlib/doc/man1/rigctld.1` (vendored manpage in this repo)
- Hamlib project docs (DeepWiki: `Hamlib/Hamlib` → “rigctl and rigctld”)

## Scope

- Covers `rigctld` TCP socket protocol (default protocol and Extended Response Protocol).
- Describes recommended parsing strategy.
- Focuses on the subset needed for MultiRig-style syncing (frequency, mode, VFO).

## Transport and framing

- **Transport:** TCP stream.
- **Port:** default `4532` (server-side option `-t` changes this).
- **Commands:** one command per line.
- **Line terminator:** send `\n`.
- **Encoding:** treat as ASCII/UTF-8 text.

Because TCP is a stream, implement buffered reading until you receive a record terminator (newline or a configured separator in ERP).

## Command formats

`rigctld` accepts:

- **Short commands:** one character, with uppercase typically meaning “set” and lowercase meaning “get”.
  - Example: `F 14250000` (set frequency), `f` (get frequency).

- **Long commands:** prepend the long name with a backslash (`\`).
  - Example: `\set_freq 14250000`, `\get_freq`.

Note: in many programming languages the backslash must be escaped in string literals (wire format is still a single `\`).

## Response protocols

`rigctld` supports two distinct response styles:

### 1) Default protocol

This is the “simple” protocol and is commonly used by Hamlib’s own “NET rigctl” backend.

- **Set commands:** respond with exactly one line:

```
RPRT x\n
```

- **Get commands:** respond with one or more **raw value lines**.
  - Example `f\n` → `14250000\n`

- **Errors:** `RPRT x\n` where **`x` is a negative number** indicating the Hamlib error code.

Important implementation note: in the default protocol, you must know how many value lines to expect for each get command (many return 1–3 lines, but some commands like `\dump_caps` can return many).

### 2) Extended Response Protocol (ERP)

ERP is intended for scripts and direct socket clients because it provides consistent framing.

#### Activation

Prepend a command with a punctuation character.

- `+` is recommended.
- Other separators such as `;`, `|`, `,` are also supported.

Long command names still require the leading backslash even with ERP.

- Example: `+\get_mode\n`

#### Record separators

- If the ERP prefix is `+`, each record ends with a newline (`\n`).
- If the ERP prefix is a separator like `;` / `|` / `,`, the entire response is on one line, separated by that character.

#### Response structure

ERP returns a “block”:

1. A **header record** echoing the command using its long command name (and any arguments).
2. Zero or more **keyed data records** formatted as `Key: Value`.
3. A terminating record: **`RPRT x`** (end-of-block marker), where `x` is the numeric return code.

Because of the explicit `RPRT` terminator, ERP is much easier to parse robustly.

## Error handling (`RPRT`)

- `RPRT 0` means success.
- `RPRT <negative>` means a Hamlib error.

Recommended approach:

- Parse `RPRT` as an integer.
- If it is not `0`, treat it as an error and surface:
  - the numeric code
  - the command that failed
  - (if using ERP) any response records preceding the `RPRT`

Do not rely on string-matching error messages; use the numeric code for control flow.

## Recommended client strategy

For a new implementation, prefer:

- **ERP with `+`** for all commands.
- Parse until `RPRT` is received.

This removes the need to maintain “how many lines does command X return?” tables.

### Parsing algorithm (ERP with `+`)

High-level algorithm per request:

1. Send: `+<command>\n` (or `+\\<long_command> ...\n`).
2. Read lines until you see a line starting with `RPRT `.
3. Convert the code after `RPRT` to an integer.
4. If non-zero → error.
5. Otherwise, parse keyed lines `Key: Value` into a dictionary (optionally preserve order).

Implementation notes:

- Always implement a read timeout.
- If the connection drops, reconnect and retry idempotent operations.
- Some commands may return no keyed lines (e.g., successful set operations).

### Suggested data model

When using ERP, a good internal result structure is:

- `command`: the command you sent
- `records`: all non-`RPRT` lines
- `kv`: parsed `Key: Value` pairs (if any)
- `rprt`: integer return code

## Common commands for MultiRig

Below are commands that are typically sufficient for syncing frequency/mode.

## Mapping rigctld/rigctl commands to Python Hamlib bindings

If you later implement a `rigctld` TCP client, you will send these commands over TCP.
If you instead implement a direct backend using Hamlib’s Python bindings (`import Hamlib`), the table below shows the rough equivalent API calls.

Important notes:

- The Python bindings are SWIG-generated wrappers over the Hamlib C API.
- Method signatures can vary slightly by Hamlib version/build. When in doubt, check at runtime with:
  - `help(Hamlib.Rig)`
  - `help(Hamlib.Rig.set_freq)` / `help(Hamlib.Rig.get_freq)` / etc.
- Prefer using Hamlib constants (e.g., `Hamlib.RIG_MODE_USB`, `Hamlib.RIG_VFO_A`) rather than string tokens.

### Rig initialization and lifecycle

Rough equivalent to starting `rigctld` and connecting a client:

- Create and configure the rig:
  - `rig = Hamlib.Rig(<model_id>)`
  - `rig.set_conf("rig_pathname", "/dev/tty...")`
  - `rig.set_conf("serial_speed", "38400")` (exact key varies)
- Open/close:
  - `rig.open()`
  - `rig.close()`

### Command mapping table

| rigctld / rigctl TCP | Meaning | Python Hamlib binding (typical) |
|---|---|---|
| `F <freq_hz>` / `\\set_freq <freq_hz>` | set frequency (Hz) | `rig.set_freq(vfo, freq_hz)` |
| `f` / `\\get_freq` | get frequency (Hz) | `rig.get_freq(vfo)` |
| `M <MODE> <PASSBAND>` / `\\set_mode ...` | set mode + passband | `rig.set_mode(mode, passband_hz)` *(some builds may also accept `vfo`)* |
| `m` / `\\get_mode` | get mode + passband | `rig.get_mode(vfo)` → `(mode, passband_hz)` |
| `V <VFO>` / `\\set_vfo <VFO>` | set current VFO | `rig.set_vfo(vfo)` |
| `v` / `\\get_vfo` | get current VFO | `rig.get_vfo()` |
| `T <PTT>` / `\\set_ptt <PTT>` | set PTT | `rig.set_ptt(vfo, ptt_state)` |
| `t` / `\\get_ptt` | get PTT | `rig.get_ptt(vfo)` |

### Token/constant mapping

#### Mode tokens

In `rigctld`, modes are exchanged as strings like `USB`, `LSB`, `CW`, `FM`, etc.

In Python, you normally use constants:

- `USB` → `Hamlib.RIG_MODE_USB`
- `LSB` → `Hamlib.RIG_MODE_LSB`
- `CW` → `Hamlib.RIG_MODE_CW`
- `CWR` → `Hamlib.RIG_MODE_CWR`
- `FM` → `Hamlib.RIG_MODE_FM`
- `AM` → `Hamlib.RIG_MODE_AM`

Passband handling:

- `0` in rigctld means “backend default”. In Python you can often pass `0` as well.
- Some Hamlib builds also expose constants like `Hamlib.RIG_PASSBAND_NORMAL` and `Hamlib.RIG_PASSBAND_NOCHANGE`.

#### VFO tokens

In `rigctld`, VFOs are exchanged as tokens like `VFOA`, `VFOB`, `currVFO`, `Main`, `Sub`, etc.

In Python, use constants:

- `VFOA` → `Hamlib.RIG_VFO_A`
- `VFOB` → `Hamlib.RIG_VFO_B`
- `currVFO` → `Hamlib.RIG_VFO_CURR`

#### PTT tokens

In `rigctld`, PTT values are numeric strings like `0` (RX) and `1` (TX).

In Python, use constants:

- `0` → `Hamlib.RIG_PTT_OFF`
- `1` → `Hamlib.RIG_PTT_ON`

### Python usage examples

#### Set frequency + mode (direct Hamlib)

```python
import Hamlib

rig = Hamlib.Rig(3073)  # example model id
rig.set_conf("rig_pathname", "/dev/cu.usbserial-XXXX")
rig.set_conf("serial_speed", "38400")
rig.open()

rig.set_vfo(Hamlib.RIG_VFO_A)
rig.set_freq(Hamlib.RIG_VFO_A, 14250000)
rig.set_mode(Hamlib.RIG_MODE_USB, 2400)

mode, pb = rig.get_mode(Hamlib.RIG_VFO_A)
freq = rig.get_freq(Hamlib.RIG_VFO_A)

rig.close()
```

#### Equivalent rigctld ERP commands (over TCP)

```text
+V VFOA
+F 14250000
+M USB 2400
+\\get_mode
+f
```

### Frequency

- **Set frequency (Hz):**
  - Short: `F <freq_hz>`
  - Long: `\set_freq <freq_hz>`

- **Get frequency:**
  - Short: `f`
  - Long: `\get_freq`

### Mode and passband

- **Set mode:**
  - Short: `M <MODE> <PASSBAND_HZ>`
  - Long: `\set_mode <MODE> <PASSBAND_HZ>`

- **Get mode:**
  - Short: `m`
  - Long: `\get_mode`

### VFO selection (important)

Many rigs/backends can get out of sync with the active VFO if a human uses the rig’s front-panel buttons.

- **Set VFO:**
  - Short: `V <VFO>`
  - Long: `\set_vfo <VFO>`

- **Get VFO:**
  - Short: `v`
  - Long: `\get_vfo`

Recommendation for syncing:

- Explicitly set the desired VFO before issuing get/set operations.

## Handling “many line” commands

Commands like `\dump_caps` can return many records.

- In default protocol, this is awkward because there is no explicit terminator.
- In ERP, you can still parse it reliably by reading until `RPRT`.

## Practical testing

### Default protocol (example)

```
$ nc localhost 4532
f
14250000
```

### ERP (recommended)

```
$ echo "+\\get_mode" | nc -w 1 localhost 4532
get_mode:
Mode: USB
Passband: 2400
RPRT 0
```

## Implementation checklist

- Use a buffered reader; never assume one `recv()` equals one line.
- Support `\n` terminated records (ERP with `+`).
- Read responses until `RPRT`.
- Parse `Key: Value` pairs.
- Implement timeouts and reconnect.
- Consider serializing access per rig if you expect multiple concurrent tasks.

## References

- Vendored manpage: `ext/hamlib/doc/man1/rigctld.1`
- DeepWiki: `Hamlib/Hamlib` → “Command-Line Tools” → “rigctl and rigctld”

## MultiRig built-in rigctl TCP listener

MultiRig includes a lightweight TCP listener that accepts a subset of the `rigctld`/`rigctl` text protocol and forwards commands to the configured rigs.

This is intended to let external apps/scripts speak “rigctl over TCP” to MultiRig, while MultiRig fans out **set** operations to all configured rigs regardless of whether they are configured as:

- `rigctld` TCP rigs (MultiRig connects to an external `rigctld`), or
- “hamlib direct” rigs (MultiRig drives a local `rigctl` subprocess).

### Listener configuration

Configured via environment variables:

- `MULTIRIG_RIGCTL_HOST` (default `127.0.0.1`)
- `MULTIRIG_RIGCTL_PORT` (default `4534`)

### Behavior

- **Set commands** are forwarded to **all rigs**.
- **Get commands** return values from the current sync source rig (`sync_source_index`).
- The server supports both:
  - Default protocol responses, and
  - ERP-style commands prefixed with punctuation (recommended: `+`).

Supported commands:

- Frequency: `F` / `f` (also `\set_freq` / `\get_freq`)
- Mode: `M` / `m` (also `\set_mode` / `\get_mode`)
- VFO: `V` / `v` (also `\set_vfo` / `\get_vfo`)
- PTT: `T` / `t` (also `\set_ptt` / `\get_ptt`)

### Testing

Using ERP (recommended):

```bash
echo "+f" | nc -w 1 127.0.0.1 4534
echo "+M USB 2400" | nc -w 1 127.0.0.1 4534
echo "+F 14250000" | nc -w 1 127.0.0.1 4534
```

Using default protocol:

```bash
printf "f\n" | nc -w 1 127.0.0.1 4534
printf "F 14250000\n" | nc -w 1 127.0.0.1 4534
```
