# The recorder runs this tape inside a fresh, staged example repository.
Set Shell "bash"
Set Width 1120
Set Height 800
Set FontFamily "Menlo"
Set FontSize 23
Set Padding 18
Set Theme "Catppuccin Mocha"
Set TypingSpeed 180ms
Set Framerate 15
Set CursorBlink false

Hide
Type@0ms "export PS1='demo $ '; unset PROMPT_COMMAND; clear; ./run-demo"
Enter
Wait+Screen /4 annotations lost their place/
Show
Sleep 3500ms

# Place the directory. Matching nested annotations follow in one decision.
Enter
Wait+Screen /From old-tools/
Sleep 3500ms
Down
Sleep 2500ms
Enter
Wait+Screen /From retired.py/
Sleep 3500ms

# Skip the intentionally deleted file, then save the updated document.
Type "s"
Wait+Screen /Placement finished/
Sleep 3500ms
Type "w"
Wait+Screen /Wrote treestamped document/
Sleep 5s

# Preserve the app's exit status without showing the recording harness.
Hide
Type "q"
Wait+Screen /CAPTURE_FINISHED/
Sleep 300ms
