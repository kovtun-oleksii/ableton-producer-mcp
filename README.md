# Ableton Producer MCP

An [MCP](https://modelcontextprotocol.io) server that lets Claude (or any MCP client) produce music in **Ableton Live**: build tracks, write MIDI, load and tweak devices, arrange sections and draw real automation, all from a chat.

It is a fork of [ahujasid/ableton-mcp](https://github.com/ahujasid/ableton-mcp) (MIT) extended for full-track production work. The fork adds arrangement editing, device-parameter control and clip and arrangement automation.

## What this fork adds

| Area | Tools |
|---|---|
| **Automation** | Read, write and clear clip envelopes (Session and Arrangement clips). Write **real Arrangement track automation** (filter sweeps, builds, fades) with `set_arrangement_automation`. |
| **Devices** | Read and set any device parameter, including on the **master track** (`track_index = -1`). Insert native devices by name at any chain position (`insert_device`). |
| **Arrangement** | Copy Session clips to the timeline, list Arrangement clips, rename them, move the playhead, create locators. |
| **Editing** | Clear notes, delete clips, create audio tracks, load audio files into clips. |
| **State** | `get_session_snapshot`: the whole set (tracks, mixer, devices, clips, notes, parameters) as JSON. |
| **Safety** | Version handshake with the Remote Script, and an installer that puts the script in the folder Live actually scans. |

## Requirements

- **Ableton Live 11 or 12.** Developed on Live 12. `insert_device` needs Live 12.1.5 or newer.
- **Python 3.10+**
- **[uv](https://docs.astral.sh/uv/getting-started/installation/)** (`brew install uv` on macOS)
- **An MCP client:** Claude Code, Claude Desktop, Cursor or similar.

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/kovtun-oleksii/ableton-producer-mcp.git
```

### 2. Install the Remote Script into Live

The MCP server talks to Live through a MIDI Remote Script (a control surface) that runs inside Live. Install it with:

```bash
uv --directory /absolute/path/to/ableton-producer-mcp run ableton-mcp-install-script
```

The script is copied to `<User Library>/Remote Scripts/AbletonMCP/`, the folder Live 10.1.13+ scans for third-party control surfaces. Useful options:

| Option | What it does |
|---|---|
| `--list-targets` | Show which Remote Scripts folders were found, then exit. |
| `--target <dir>` | Install into an explicit folder. |
| `--force` | Overwrite even if `ABLETON_MCP_SKIP_SCRIPT_INSTALL` is set. |
| `--legacy` | Also copy into the old `User Remote Scripts` preference folders. Live does not scan these for Python scripts, so you rarely need it. |

### 3. Enable the control surface in Live

1. Restart Live.
2. Open **Settings → Link, Tempo & MIDI**. In Live 11 this is **Preferences → Link Tempo MIDI**.
3. Under **Control Surface**, pick **AbletonMCP**.
4. Set **Input** and **Output** to **None**.

The script listens on `localhost:9877`.

### 4. Connect your MCP client

**Claude Code**

```bash
claude mcp add AbletonMCP -- uv --directory /absolute/path/to/ableton-producer-mcp run ableton-mcp
```

**Claude Desktop.** Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "AbletonMCP": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/ableton-producer-mcp", "run", "ableton-mcp"]
    }
  }
}
```

**Cursor and other clients:** use the same command, `uv --directory /absolute/path/to/ableton-producer-mcp run ableton-mcp`.

Run only **one** MCP client against Live at a time, because they share the same socket.

### 5. Check the connection

With Live open, ask your assistant *"What's in my Live set?"*. It should call `get_session_info` and report the tempo and tracks.

You can also query the Remote Script directly, bypassing the MCP server. Run this from the repository folder:

```bash
python3 scripts/live_call.py get_script_info
```

The reply should report Remote Script version **1.8.3**. If the server warns about a version mismatch, run step 2 again and restart Live.

## Updating

```bash
git -C /absolute/path/to/ableton-producer-mcp pull
```

If the Remote Script changed, run the installer from step 2 again. Then restart Live, or re-select AbletonMCP under Control Surface.

## Tools

Each tool also takes an optional `user_prompt` argument.

**Session and transport**
`get_session_info`, `get_remote_script_info`, `get_session_snapshot`, `set_tempo`, `start_playback`, `stop_playback`, `switch_to_arrangement_view`, `set_arrangement_time`

**Tracks**
`get_track_info`, `create_midi_track`, `create_audio_track`, `set_track_name`

**Clips and notes (Session view)**
`create_clip`, `add_notes_to_clip`, `get_clip_notes`, `clear_notes_from_clip`, `set_clip_name`, `delete_clip`, `fire_clip`, `stop_clip`, `create_audio_clip`

**Arrangement**
`duplicate_to_arrangement`, `get_arrangement_clips`, `set_arrangement_clip_name`, `create_locator`

**Devices and browser**
`get_device_parameters`, `set_device_parameter`, `insert_device`, `load_instrument_or_effect`, `load_drum_kit`, `get_browser_tree`, `get_browser_items_at_path`

**Automation**
`get_clip_automation`, `set_clip_automation`, `clear_clip_automation`, `set_arrangement_automation`, `clear_arrangement_automation`

**Feedback and dataset** (opt-in, see [Telemetry and data](#telemetry-and-data))
`set_dataset_consent`, `submit_intent`, `rate_last_action`, `prefer_candidate`, `reject_last_action`, `record_audition`

### Units and conventions

- **Time** is in beats (quarter notes). In 4/4, bar *N* starts at beat `(N − 1) × 4`. Notes look like `{"pitch": 60, "start_time": 0.0, "duration": 0.5, "velocity": 96}`. Middle C is 60 (C3 in Live).
- **Parameter values** use each parameter's own `min..max` range. Call `get_device_parameters` first to find the index, range and current display value.
- **Indices** shift when tracks or devices are added or removed. Look things up by name right before each change, especially if you are editing the set at the same time.

## Automation

**Clip envelopes:** `set_clip_automation` writes a curve into one clip, with times relative to the clip start:

```json
{"track_index": 2, "clip_index": 0, "device_index": 1, "parameter_index": 4,
 "points": [{"time": 0, "value": 0.2}, {"time": 16, "value": 0.8}]}
```

Points ramp linearly. Add `"step": true` to a point to hold its value until the next point, which gives a jump.

**Arrangement automation:** Live's API cannot create envelopes inside Arrangement clips. `set_arrangement_automation` works around this:

1. Each Arrangement clip in the curve's span is rebuilt in a spare Session slot, with the same notes plus the envelope.
2. The rebuilt clip is copied back onto the timeline.
3. Live converts the envelope into real track automation.

Times are absolute Arrangement beats. Things to know:

- The track needs **one empty Session slot** and **MIDI clips** covering the span. Audio clips, and clips looped or trimmed in the Arrangement, are skipped and reported.
- Rebuilding a clip can reset that span for other automated parameters on the same track. Put all curves for the same span into **one** call (or one plan job, see below), then read the values back.
- Group tracks and audio tracks that monitor an input can't be automated through the API.

For batch jobs, `scripts/arrangement_automation.py plan.json` runs the same technique from the command line. The plan format is described at the top of the script.

## Tips and limits

- **Session overrides Arrangement.** After firing Session clips, press **Back to Arrangement** in Live or the timeline stays muted.
- **Read parameter values with the transport stopped.** During playback, readings lag about one beat.
- **Loading a device arms the track.** Loading a device or sample selects that track and arms it; disarm it afterwards.
- **`get_session_snapshot` can be very large.** Pass `include_notes=false` and `include_params=false` when you only need the structure.
- **Not possible through this server:** deleting or muting tracks, moving devices within a chain, choosing a sidechain source ("Audio From"). Do these by hand in Live.

## Configuration

| Variable | Default | Used by |
|---|---|---|
| `ABLETON_HOST` / `ABLETON_PORT` | `localhost` / `9877` | MCP server |
| `ABLETON_MCP_HOST` / `ABLETON_MCP_PORT` | `127.0.0.1` / `9877` | `scripts/*.py` |
| `DISABLE_TELEMETRY`, `ABLETON_MCP_DISABLE_TELEMETRY`, `MCP_DISABLE_TELEMETRY` | unset | Kill switch: set any of them to `true` and nothing is sent. |
| `ABLETON_MCP_SKIP_SCRIPT_INSTALL` | unset | Installer skips the copy unless `--force` is given. |

## Telemetry and data

A fresh clone **sends nothing**. Telemetry and dataset recording need credentials in `MCP_Server/config.py`. That file is not part of this repository and is ignored by git.

The feedback and dataset tools record only after the user explicitly agrees via `set_dataset_consent`. The kill-switch variables above override any consent.

## Development

```bash
python3 -m unittest discover -s tests
```

- `scripts/live_call.py` sends one raw command to the Remote Script and prints the reply. Use it to smoke-test script changes in a running Live.
- `scripts/live_names.py` holds name-based track and device helpers, setters that take display values (such as dB), and a peak meter.
- `scripts/arrangement_automation.py` writes Arrangement automation from a JSON plan.
- `MCP_Server/bundled_ableton_remote_script/AbletonMCP_init.py` is the Remote Script that ships with the package. After editing it, run the installer again and reload the control surface in Live.

## Credits and license

MIT, see [LICENSE](LICENSE). Based on [ableton-mcp](https://github.com/ahujasid/ableton-mcp) by Siddharth Ahuja. This is a third-party project and is not affiliated with or endorsed by Ableton.
