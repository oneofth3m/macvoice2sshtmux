-- Sample Hammerspoon config for macvoice2sshtmux.
-- Bind Cmd+Ctrl+V to start/stop capture lifecycle in the Python service.

local toggleState = false

local function sendEvent(event)
  os.execute(string.format("voice2tmux event --event %s >/dev/null 2>&1", event))
end

hs.hotkey.bind({"cmd", "ctrl"}, "V", function()
  if toggleState then
    sendEvent("stop")
  else
    sendEvent("start")
  end
  toggleState = not toggleState
end)

hs.hotkey.bind({"cmd", "ctrl"}, "B", function()
  sendEvent("confirm")
end)

