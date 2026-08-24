Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\user\Downloads\telegram_test_platform_full_project"
WshShell.Run "python -m app.main", 0, False
