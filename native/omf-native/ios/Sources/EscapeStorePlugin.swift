import Foundation
import Capacitor
import StoreKit

/// Compra única "Escape completo" con StoreKit 2 (sin SDK de terceros).
/// El JS usa el id "escape_full"; aquí se mapea al product id de App Store Connect.
@objc(EscapeStorePlugin)
public class EscapeStorePlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "EscapeStorePlugin"
    public let jsName = "EscapeStore"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "owned", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "products", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "buy", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "restore", returnType: CAPPluginReturnPromise),
    ]

    private let fullId = "com.onemorefloor.escape.full"
    private var updates: Task<Void, Never>?

    private func productId(_ id: String?) -> String {
        guard let id = id, !id.isEmpty, id != "escape_full" else { return fullId }
        return id
    }

    override public func load() {
        // Compras hechas fuera de la app (Ask to Buy, otro dispositivo, reembolsos).
        updates = Task.detached { [weak self] in
            for await result in Transaction.updates {
                if case .verified(let t) = result {
                    await t.finish()
                    let owned = await self?.isOwned() ?? false
                    self?.notifyListeners("ownedChanged", data: ["owned": owned])
                }
            }
        }
    }

    deinit { updates?.cancel() }

    private func isOwned() async -> Bool {
        for await result in Transaction.currentEntitlements {
            if case .verified(let t) = result, t.productID == fullId, t.revocationDate == nil { return true }
        }
        return false
    }

    @objc func owned(_ call: CAPPluginCall) {
        Task { call.resolve(["owned": await isOwned()]) }
    }

    @objc func products(_ call: CAPPluginCall) {
        Task {
            do {
                let ps = try await Product.products(for: [fullId])
                if let p = ps.first {
                    call.resolve(["ok": true, "id": "escape_full", "price": p.displayPrice,
                                  "title": p.displayName, "description": p.description])
                } else {
                    call.resolve(["ok": false, "error": "Producto no disponible"])
                }
            } catch {
                call.resolve(["ok": false, "error": error.localizedDescription])
            }
        }
    }

    @objc func buy(_ call: CAPPluginCall) {
        let pid = productId(call.getString("id"))
        Task {
            do {
                guard let product = try await Product.products(for: [pid]).first else {
                    call.resolve(["owned": await isOwned(), "error": "Producto no disponible"]); return
                }
                let result: Product.PurchaseResult
                if #available(iOS 17.0, *), let scene = await MainActor.run(body: { self.bridge?.viewController?.view.window?.windowScene }) {
                    result = try await product.purchase(confirmIn: scene)
                } else {
                    result = try await product.purchase()
                }
                switch result {
                case .success(let verification):
                    if case .verified(let t) = verification {
                        await t.finish()
                        call.resolve(["owned": true])
                    } else {
                        call.resolve(["owned": false, "error": "Compra no verificada"])
                    }
                case .userCancelled:
                    call.resolve(["owned": await isOwned(), "cancelled": true])
                case .pending:
                    call.resolve(["owned": false, "pending": true])
                @unknown default:
                    call.resolve(["owned": await isOwned()])
                }
            } catch {
                let owned = await self.isOwned()
                call.resolve(["owned": owned, "error": "\(error)"])
            }
        }
    }

    @objc func restore(_ call: CAPPluginCall) {
        Task {
            do { try await AppStore.sync() } catch {
                call.resolve(["owned": await isOwned(), "error": error.localizedDescription]); return
            }
            call.resolve(["owned": await isOwned()])
        }
    }
}
