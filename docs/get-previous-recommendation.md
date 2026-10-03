# getPreviousRecommendation — only after login

`getPreviousRecommendation` is bound on the supervisor and may run **only after login**.

In this repo the tool is named **`getPreviousRecommendation`** (singular). Enforcement is **not** an MCP ACL and **not** a prompt-only rule. The guest supervisor never receives the tool object.

## How it is enforced

The graph compiles **two** supervisor hops. Both run **inside the supervisor container**. Portfolio is a **separate A2A container**; `logged_in` is not.

```
START → supervisor (guest) → portfolio (A2A) → logged_in → …
```

**Guest** (`logged_in=False`) is built with **no tools**:

```python
supervisor_node = build_supervisor_node(model, logged_in=False)
```

**Logged-in** is the only hop that gets `getPreviousRecommendation`:

```python
logged_in_node = build_supervisor_node(
    model, logged_in=True, tools=read_tools
)
```

`read_tools` is that one GET tool (MCP, python `@tool`, or skills — same name). `create_agent` with those tools runs only when `logged_in and tools` (`agents/supervisor/agent.py`).

The guest hop cannot call GET even if Gemini asks for it: there is nothing bound to call. It can only route `portfolio` | `finish`. Last-rec / research asks before login are sent to **portfolio** first (`enforce_guest_routing`).

**Logged-in is unreachable until portfolio has run.** The only edge into that node is `portfolio → logged_in`. Portfolio is what logs in and sets `user_id`.

Same binding in every `TOOL_MODE`. Packaging of GET changes; who receives the tool does not.

Save is a separate graph hop after research, not this tool.
