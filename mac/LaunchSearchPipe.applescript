on run
	tell application "Finder"
		set appFile to (path to me as alias)
		set parentFolder to container of appFile as alias
	end tell
	set projectPOSIX to POSIX path of parentFolder
	set startCmd to "cd " & quoted form of projectPOSIX & " && chmod +x ./pipeline/start.sh 2>/dev/null; exec ./pipeline/start.sh"
	tell application "Terminal"
		activate
		do script startCmd
	end tell
end run
