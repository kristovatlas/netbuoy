import Cocoa

// NetbuoyVPNHelper: Clicks Quick Connect in ProtonVPN.
// Grant accessibility to this app only (System Settings > Privacy & Security > Accessibility).

func clickQuickConnect() {
    let workspace = NSWorkspace.shared
    let appName = "ProtonVPN"

    // Launch ProtonVPN if not running
    if !workspace.runningApplications.contains(where: { $0.bundleIdentifier == "ch.protonvpn.mac" }) {
        workspace.launchApplication(appName)
        Thread.sleep(forTimeInterval: 2.0)
    }

    // Bring to front
    if let app = workspace.runningApplications.first(where: { $0.bundleIdentifier == "ch.protonvpn.mac" }) {
        app.activate(options: .activateIgnoringOtherApps)
        Thread.sleep(forTimeInterval: 0.5)
    }

    // Find ProtonVPN in accessibility
    guard let appElement = findProtonVPNApp() else {
        fputs("Error: Could not find ProtonVPN process in accessibility API\n", stderr)
        exit(1)
    }

    // Find window
    var windowValue: CFTypeRef?
    AXUIElementCopyAttributeValue(appElement, kAXWindowsAttribute as CFString, &windowValue)
    guard let windows = windowValue as? [AXUIElement], let window = windows.first else {
        fputs("Error: Could not find ProtonVPN window\n", stderr)
        exit(1)
    }

    // Find and click Quick Connect button
    if let button = findButton(in: window, named: "Quick Connect") {
        AXUIElementPerformAction(button, kAXPressAction as CFString)
    } else {
        fputs("Error: Could not find Quick Connect button\n", stderr)
        exit(1)
    }
}

func findProtonVPNApp() -> AXUIElement? {
    let apps = NSWorkspace.shared.runningApplications
    guard let app = apps.first(where: { $0.bundleIdentifier == "ch.protonvpn.mac" }) else {
        return nil
    }
    return AXUIElementCreateApplication(app.processIdentifier)
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
