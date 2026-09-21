on run
    -- Persisted run-handler globals would modify the signed script.
    local pythonExecutable, bootstrapScript, overridesFile, commandText, errorMessage, errorNumber
    set pythonExecutable to @@PYTHON@@
    set bootstrapScript to @@SCRIPT@@
    set overridesFile to @@OVERRIDES@@
    set commandText to quoted form of pythonExecutable & " " & quoted form of bootstrapScript & " --launch --overrides " & quoted form of overridesFile
    try
        return do shell script commandText
    on error errorMessage number errorNumber
        activate
        display alert "Claude Bootstrap · 未能完成启动" message (errorMessage & return & return & "如果 Claude 已经打开，请先保存工作并用 ⌘Q 完全退出，再点击此图标。此启动器不会强制退出 Claude。") as warning buttons {"好"} default button "好"
    end try
end run
