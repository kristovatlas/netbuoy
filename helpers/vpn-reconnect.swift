import Cocoa

// NetbuoyVPNHelper: Clicks Quick Connect in ProtonVPN.
// Grant accessibility to this app only (System Settings > Privacy & Security > Accessibility).

func clickQuickConnect() {
    let workspace = NSWorkspace.shared

    // Check accessibility permission
    let trusted = AXIsProcessTrustedWithOptions(
        [kAXTrustedCheckOptionPrompt.takeUnretainedValue(): false] as CFDictionary
    )
    if !trusted {
        fputs("Error: Accessibility permission not granted for NetbuoyVPNHelper\n", stderr)
        fputs("Grant access in: System Settings > Privacy & Security > Accessibility\n", stderr)
        exit(1)
    }

    // Launch ProtonVPN if not running
    if !workspace.runningApplications.contains(where: { $0.bundleIdentifier == "ch.protonvpn.mac" }) {
        workspace.launchApplication("ProtonVPN")
        Thread.sleep(forTimeInterval: 2.0)
    }

    // Bring to front
    guard let app = workspace.runningApplications.first(where: { $0.bundleIdentifier == "ch.protonvpn.mac" }) else {
        fputs("Error: ProtonVPN is not running\n", stderr)
        exit(1)
    }
    app.activate(options: .activateIgnoringOtherApps)
    Thread.sleep(forTimeInterval: 1.0)

    let appElement = AXUIElementCreateApplication(app.processIdentifier)

    // Find window — retry a few times in case the window is still loading
    var window: AXUIElement?
    for _ in 0..<5 {
        var windowValue: CFTypeRef?
        let result = AXUIElementCopyAttributeValue(appElement, kAXWindowsAttribute as CFString, &windowValue)
        if result == .success, let windows = windowValue as? [AXUIElement], let w = windows.first {
            window = w
            break
        }
        fputs("Waiting for ProtonVPN window (status: \(result.rawValue))...\n", stderr)
        Thread.sleep(forTimeInterval: 1.0)
    }

    guard let window = window else {
        // Print diagnostic info
        var roleValue: CFTypeRef?
        let roleResult = AXUIElementCopyAttributeValue(appElement, kAXRoleAttribute as CFString, &roleValue)
        fputs("Error: Could not find ProtonVPN window\n", stderr)
        fputs("App role query result: \(roleResult.rawValue), value: \(roleValue ?? "nil" as CFString)\n", stderr)
        fputs("PID: \(app.processIdentifier), bundleID: \(app.bundleIdentifier ?? "nil")\n", stderr)
        exit(1)
    }

    // Find and click Quick Connect button
    if let button = findButton(in: window, named: "Quick Connect") {
        AXUIElementPerformAction(button, kAXPressAction as CFString)
    } else {
        fputs("Error: Could not find Quick Connect button\n", stderr)
        // Dump top-level children for debugging
        var childrenValue: CFTypeRef?
        AXUIElementCopyAttributeValue(window, kAXChildrenAttribute as CFString, &childrenValue)
        if let children = childrenValue as? [AXUIElement] {
            for child in children {
                var role: CFTypeRef?
                var title: CFTypeRef?
                AXUIElementCopyAttributeValue(child, kAXRoleAttribute as CFString, &role)
                AXUIElementCopyAttributeValue(child, kAXTitleAttribute as CFString, &title)
                fputs("  child: role=\(role ?? "nil" as CFString) title=\(title ?? "nil" as CFString)\n", stderr)
            }
        }
        exit(1)
    }
}

func findButton(in element: AXUIElement, named name: String) -> AXUIElement? {
    var roleValue: CFTypeRef?
    var nameValue: CFTypeRef?

    AXUIElementCopyAttributeValue(element, kAXRoleAttribute as CFString, &roleValue)
    AXUIElementCopyAttributeValue(element, kAXTitleAttribute as CFString, &nameValue)

    if let role = roleValue as? String, role == kAXButtonRole as String,
       let title = nameValue as? String, title == name {
        return element
    }

    // Also check description attribute (some buttons use it instead of title)
    AXUIElementCopyAttributeValue(element, kAXDescriptionAttribute as CFString, &nameValue)
    if let role = roleValue as? String, role == kAXButtonRole as String,
       let desc = nameValue as? String, desc == name {
        return element
    }

    // Recurse into children
    var childrenValue: CFTypeRef?
    AXUIElementCopyAttributeValue(element, kAXChildrenAttribute as CFString, &childrenValue)
    if let children = childrenValue as? [AXUIElement] {
        for child in children {
            if let found = findButton(in: child, named: name) {
                return found
            }
        }
    }

    return nil
}

clickQuickConnect()
