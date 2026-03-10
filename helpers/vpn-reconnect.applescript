-- NetbuoyVPNHelper: Clicks Quick Connect in ProtonVPN.
-- Grant accessibility permissions to this app only (System Settings > Privacy & Security > Accessibility).

try
    tell application "ProtonVPN" to activate
    delay 1
    tell application "System Events"
        click button "Quick Connect" of window 1 of process "ProtonVPN"
    end tell
on error
    -- ProtonVPN not installed or window not available
end try
