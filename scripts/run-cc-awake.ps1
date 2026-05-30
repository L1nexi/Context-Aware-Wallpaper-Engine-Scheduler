param(
    [Parameter(Mandatory = $true, Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Prompt
)

Add-Type @"
using System;
using System.Runtime.InteropServices;

public class Awake {
    [DllImport("kernel32.dll")]
    private static extern uint SetThreadExecutionState(uint esFlags);

    public static void KeepSystemAwake() {
        SetThreadExecutionState(0x80000000u | 0x00000001u);
    }

    public static void RestoreSleep() {
        SetThreadExecutionState(0x80000000u);
    }
}
"@

$projectRoot = Split-Path $PSScriptRoot -Parent
$promptText = $Prompt -join " "

[Awake]::KeepSystemAwake()

try {
    Push-Location $projectRoot

    claude -p --permission-mode auto --output-format stream-json --verbose $promptText |
    jq -Rr --unbuffered '
      fromjson? as $j |
      if $j.type == "assistant" then
        $j.message.content[]? |
          if .type == "text" then
            .text
          elif .type == "tool_use" then
            "[tool] " + .name + " " + (.input | tostring)
          else
            empty
          end
      elif $j.type == "result" then
        "[result] " + ($j.subtype // "done")
      else
        empty
      end
    '
}
finally {
    Pop-Location
    [Awake]::RestoreSleep()
}