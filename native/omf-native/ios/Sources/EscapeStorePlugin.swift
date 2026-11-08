import Foundation
import Capacitor
import StoreKit

/// Compra única "Escape completo" con StoreKit 2 (sin SDK de terceros).
/// El JS usa el id "escape_full"; aquí se mapea al product id de App Store Connect.
/// v166 (2026-11-08): también las 5 colecciones de aspectos de pago (col_*). "owned" sigue significando solo
/// Escape completo (el JS antiguo depende de eso); las colecciones van en "ids" y "items", y "fullDate" es la fecha
/// original de compra de Escape completo en ms (para regalar las colecciones a quien lo compró antes).
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
    private let colIds = ["com.onemorefloor.escape.col_cuerda", "com.onemorefloor.escape.col_estrellas",
                          "com.onemorefloor.escape.col_brasa", "com.onemorefloor.escape.col_cristal",
                          "com.onemorefloor.escape.col_todas"]
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
                    if let ent = await self?.entitlements() {
                        self?.notifyListeners("ownedChanged", data: ent)
                    }
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

    /// Escape completo + colecciones que tiene esta cuenta ahora mismo.
    private func entitlements() async -> [String: Any] {
        var full = false, ids: [String] = [], fullDate: Double = 0
        for await result in Transaction.currentEntitlements {
            guard case .verified(let t) = result, t.revocationDate == nil else { continue }
            if t.productID == fullId { full = true; fullDate = t.originalPurchaseDate.timeIntervalSince1970 * 1000 }
            else if colIds.contains(t.productID) { ids.append(t.productID) }
        }
        var out: [String: Any] = ["owned": full, "ids": ids]
        if full { out["fullDate"] = fullDate }
        return out
    }

    @objc func owned(_ call: CAPPluginCall) {
        Task { call.resolve(await entitlements()) }
    }

    @objc func products(_ call: CAPPluginCall) {
        Task {
            do {
                let ps = try await Product.products(for: [fullId] + colIds)
                var items: [String: Any] = [:]
                for p in ps where p.id != fullId { items[p.id] = ["price": p.displayPrice, "title": p.displayName] }
                if let p = ps.first(where: { $0.id == fullId }) {
                    let store = await Storefront.current?.countryCode ?? ""
                    call.resolve(["ok": true, "id": "escape_full", "price": p.displayPrice,
                                  "title": p.displayName, "description": p.description,
                                  "currency": p.priceFormatStyle.currencyCode, "storefront": store, "items": items])
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
                        var out = await entitlements()
                        out["bought"] = t.productID
                        if t.productID == fullId { out["owned"] = true }
                        call.resolve(out)
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
            call.resolve(await entitlements())
        }
    }
}
