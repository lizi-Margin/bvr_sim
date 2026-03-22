# MCP Server Reference

PinchTab exposes a Model Context Protocol (MCP) server over **stdio JSON-RPC 2.0** (MCP spec 2025-11-25). This lets AI agents (Claude, GPT-4o, etc.) control a browser directly through their tool-calling interface.

---

## Configuration

Add PinchTab to your MCP client config:

```json
{
  "mcpServers": {
    "pinchtab": {
      "command": "pinchtab",
      "args": ["mcp"]
    }
  }
}
```

For Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "pinchtab": {
      "command": "pinchtab",
      "args": ["mcp"],
      "env": {
        "PINCHTAB_PORT": "9867"
      }
    }
  }
}
```

PinchTab must be running (`pinchtab start`) before the MCP server can proxy requests. The MCP server communicates with the PinchTab HTTP API at `localhost:9867` by default.

---

## Available Tools (21 total)

All tool names are prefixed with `pinchtab_`.

### Navigation
| Tool | Description |
|------|-------------|
| `pinchtab_navigate` | Navigate to a URL. Required param: `url`. Optional: `tabId`. |
| `pinchtab_health` | Check server health. No params. |

### Page Reading
| Tool | Description |
|------|-------------|
| `pinchtab_snapshot` | Accessibility tree. Optional: `interactive`, `compact`, `diff`, `selector`, `tabId`. |
| `pinchtab_screenshot` | Capture screenshot. Optional: `quality`, `tabId`. Returns base64 image. |
| `pinchtab_get_text` | Extract readable page text. Optional: `raw`, `tabId`. |
| `pinchtab_find` | Find elements by text or CSS selector. Required: `query`. Optional: `tabId`. |
| `pinchtab_eval` | Execute JavaScript. Required: `expression`. Optional: `tabId`. Needs `security.allowEvaluate: true`. |
| `pinchtab_pdf` | Export page as PDF. Optional: `landscape`, `scale`, `pageRanges`, `tabId`. Returns base64 PDF. |
| `pinchtab_cookies` | Get cookies for current page. Optional: `tabId`. |

### Interaction
| Tool | Description |
|------|-------------|
| `pinchtab_click` | Click element by ref. Required: `ref`. Optional: `tabId`. |
| `pinchtab_type` | Type text keystroke-by-keystroke. Required: `ref`, `text`. Optional: `tabId`. |
| `pinchtab_fill` | Fill input via JS dispatch (React/Vue/Angular safe). Required: `ref`, `value`. Optional: `tabId`. |
| `pinchtab_press` | Press a named key (`Enter`, `Tab`, `Escape`, etc.). Required: `key`. Optional: `tabId`. |
| `pinchtab_hover` | Hover over element. Required: `ref`. Optional: `tabId`. |
| `pinchtab_focus` | Focus an element. Required: `ref`. Optional: `tabId`. |
| `pinchtab_select` | Select dropdown option. Required: `ref`, `value`. Optional: `tabId`. |
| `pinchtab_scroll` | Scroll page or element. Optional: `ref`, `pixels`, `tabId`. |

### Tab Management
| Tool | Description |
|------|-------------|
| `pinchtab_list_tabs` | List all open tabs. No params. |
| `pinchtab_close_tab` | Close a tab. Optional: `tabId` (closes current if omitted). |

### Utility
| Tool | Description |
|------|-------------|
| `pinchtab_wait` | Wait N milliseconds. Required: `ms` (max 30000). |
| `pinchtab_wait_for_selector` | Wait for CSS selector to appear. Required: `selector`. Optional: `timeout`, `tabId`. |

---

## Element Refs

`pinchtab_snapshot` returns an accessibility tree with element refs like `e5`, `e12`. These refs are required by all interaction tools (`click`, `type`, `fill`, `hover`, etc.).

**Important:** Refs are ephemeral. They expire after navigation or significant DOM updates. Always re-call `pinchtab_snapshot` after a page load before using refs in interactions.

---

## What MCP Cannot Do

The MCP surface is intentionally scoped to browser automation. The following are **not available** via MCP tools:

| Capability | Status | Alternative |
|------------|--------|-------------|
| Create/edit/delete profiles | ❌ Not available | Use `pinchtab profile` CLI or HTTP API |
| Configure the scheduler | ❌ Not available | Use `pinchtab schedule` CLI |
| Modify stealth / fingerprint settings | ❌ Not available | Edit config file directly |
| Start or stop the PinchTab server | ❌ Not available | Use `pinchtab start` / `pinchtab stop` CLI |
| Manage fleet instances | ❌ Not available | Use `pinchtab instances` CLI |
| Read/write PinchTab config | ❌ Not available | Edit `~/.pinchtab/config.yaml` directly |

If you need these capabilities in an agent workflow, use the CLI commands alongside the MCP tools, or call the PinchTab HTTP API directly.

---

## Error Handling

MCP tools surface errors as tool errors (not protocol-level errors). Common cases:

| Error | Cause | Fix |
|-------|-------|-----|
| Connection refused | PinchTab not running | `pinchtab start` |
| `ref not found` | Stale element ref | Re-run `pinchtab_snapshot` |
| `evaluate not allowed` (403) | `security.allowEvaluate` is false | Enable in config or use `find`/`snap` instead |
| `invalid URL` | Missing `http://` or `https://` | Include full scheme in URL |

---

## Related

- [MCP Tools Full Parameter Reference](../../docs/reference/mcp-tools.md)
- [API Reference](api.md)
- [Agent Optimization Playbook](agent-optimization.md)
