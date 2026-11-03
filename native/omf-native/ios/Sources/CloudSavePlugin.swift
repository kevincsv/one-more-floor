import Foundation
import Capacitor

/// Copia automática en iCloud (NSUbiquitousKeyValueStore, hasta 1 MB). No necesita Game Center.
@objc(CloudSavePlugin)
public class CloudSavePlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "CloudSavePlugin"
    public let jsName = "CloudSave"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "get", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "set", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "remove", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "synchronize", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "status", returnType: CAPPluginReturnPromise),
    ]

    private let store = NSUbiquitousKeyValueStore.default

    override public func load() {
        NotificationCenter.default.addObserver(self, selector: #selector(changed(_:)),
            name: NSUbiquitousKeyValueStore.didChangeExternallyNotification, object: store)
        store.synchronize()
    }

    @objc private func changed(_ n: Notification) {
        let keys = n.userInfo?[NSUbiquitousKeyValueStoreChangedKeysKey] as? [String] ?? []
        let reason = n.userInfo?[NSUbiquitousKeyValueStoreChangeReasonKey] as? Int ?? -1
        let names = [NSUbiquitousKeyValueStoreServerChange: "server",
                     NSUbiquitousKeyValueStoreInitialSyncChange: "initial",
                     NSUbiquitousKeyValueStoreQuotaViolationChange: "quota",
                     NSUbiquitousKeyValueStoreAccountChange: "account"]
        notifyListeners("changed", data: ["keys": keys, "reason": names[reason] ?? "unknown"])
    }

    /// El almacén key-value funciona aunque iCloud Drive esté apagado (solo necesita sesión de iCloud),
    /// así que available es siempre true; iCloudDrive se informa aparte por si el juego quiere mostrarlo.
    @objc func status(_ call: CAPPluginCall) {
        call.resolve(["ok": true, "available": true,
                      "iCloudDrive": FileManager.default.ubiquityIdentityToken != nil,
                      "synced": store.synchronize()])
    }

    /// { key } -> { value: string | null }
    @objc func get(_ call: CAPPluginCall) {
        guard let key = call.getString("key") else { call.reject("key requerido"); return }
        if let v = store.string(forKey: key) { call.resolve(["value": v]) }
        else { call.resolve(["value": NSNull()]) }
    }

    /// { key, value: string }
    @objc func set(_ call: CAPPluginCall) {
        guard let key = call.getString("key"), let value = call.getString("value") else {
            call.reject("key y value (string) requeridos"); return
        }
        store.set(value, forKey: key)
        call.resolve(["ok": store.synchronize()])
    }

    @objc func remove(_ call: CAPPluginCall) {
        guard let key = call.getString("key") else { call.reject("key requerido"); return }
        store.removeObject(forKey: key)
        call.resolve(["ok": store.synchronize()])
    }

    @objc func synchronize(_ call: CAPPluginCall) {
        call.resolve(["ok": store.synchronize()])
    }
}
