on run
    -- Persisted run-handler globals would modify the signed script.
    local configCommand, bootstrapScript, machineFile, commandText, errorMessage, errorNumber
    set configCommand to @@COMMAND@@
    set bootstrapScript to POSIX path of (path to resource "launch.command" in directory "Bootstrap")
    set machineFile to @@MACHINE@@
    set commandText to "/bin/zsh " & quoted form of bootstrapScript & " --claude-config " & quoted form of configCommand & " --machine " & quoted form of machineFile
    try
        return do shell script commandText
    on error errorMessage number errorNumber
        activate
        display alert "Claude Bootstrap · 未能完成启动" message errorMessage as warning buttons {"好"} default button "好"
    end try
end run
