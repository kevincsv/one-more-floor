import Foundation
import Capacitor
import GameKit

/// Game Center con la misma API que PlayGamesPlugin (Android).
/// Los ids del juego ("m100", "height"...) se mapean a "omf_<id>" en App Store Connect.
@objc(GameCenterPlugin)
public class GameCenterPlugin: CAPPlugin, CAPBridgedPlugin, GKGameCenterControllerDelegate {
    public let identifier = "GameCenterPlugin"
    public let jsName = "GameCenter"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "status", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "signIn", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "unlock", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "progress", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "submitScore", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "showAchievements", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "showLeaderboard", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "resetAchievements", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "loadTop", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "pendingActivity", returnType: CAPPluginReturnPromise),
    ]

    private let prefix = "omf_"
    private var pendingSignIn: [CAPPluginCall] = []
    private var handlerInstalled = false
    /// Retos y actividades de Game Center (iOS 26+): la que el jugador abrió y el juego aún no ha leído.
    fileprivate var pendingAct: [String: Any]? = nil
    private var actListener: NSObject? = nil

    private func gcId(_ raw: String?) -> String? {
        guard let raw = raw, !raw.isEmpty else { return nil }
        return raw.hasPrefix(prefix) ? raw : prefix + raw
    }

    private func result(_ ok: Bool, _ extra: [String: Any] = [:]) -> [String: Any] {
        var r: [String: Any] = ["ok": ok, "signedIn": GKLocalPlayer.local.isAuthenticated]
        extra.forEach { r[$0.key] = $0.value }
        return r
    }

    override public func load() {
        // Apple recomienda autenticar al arrancar; si ya hay sesión en el sistema entra sin interfaz.
        DispatchQueue.main.async { self.installHandler() }
    }

    private func installHandler() {
        if handlerInstalled { return }
        handlerInstalled = true
        GKLocalPlayer.local.authenticateHandler = { [weak self] vc, error in
            guard let self = self else { return }
            if let vc = vc, !self.pendingSignIn.isEmpty {
                self.bridge?.viewController?.present(vc, animated: true)
                return
            }
            let calls = self.pendingSignIn
            self.pendingSignIn.removeAll()
            let r = self.result(error == nil && GKLocalPlayer.local.isAuthenticated,
                                error.map { ["error": $0.localizedDescription] } ?? [:])
            calls.forEach { $0.resolve(r) }
            if GKLocalPlayer.local.isAuthenticated { self.registerActivityListener() }
        }
    }

    private func registerActivityListener() {
        guard actListener == nil else { return }
        if #available(iOS 26.0, *) {
            let l = OmfActivityListener(plugin: self)
            actListener = l
            GKLocalPlayer.local.register(l)
        }
    }

    fileprivate func gotActivity(id: String, party: String) {
        let data: [String: Any] = ["id": id, "party": party]
        pendingAct = data
        notifyListeners("gameActivity", data: data, retainUntilConsumed: true)
    }

    /// Devuelve una vez la actividad pendiente ({ id, party }) o {} si no hay.
    @objc func pendingActivity(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            let a = self.pendingAct ?? [:]
            self.pendingAct = nil
            call.resolve(a)
        }
    }

    @objc func status(_ call: CAPPluginCall) {
        call.resolve(result(true))
    }

    @objc func signIn(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            if GKLocalPlayer.local.isAuthenticated { call.resolve(self.result(true)); return }
            self.pendingSignIn.append(call)
            if self.handlerInstalled {
                // Reinstalar el handler fuerza a iOS a volver a pedir la interfaz de inicio de sesión.
                self.handlerInstalled = false
            }
            self.installHandler()
        }
    }

    private func report(_ id: String, percent: Double, _ call: CAPPluginCall) {
        guard GKLocalPlayer.local.isAuthenticated else { call.resolve(result(false)); return }
        let a = GKAchievement(identifier: id)
        a.percentComplete = min(100, max(0, percent))
        a.showsCompletionBanner = true
        GKAchievement.report([a]) { error in
            call.resolve(self.result(error == nil, error.map { ["error": $0.localizedDescription] } ?? [:]))
        }
    }

    /// { id: "noise" }
    @objc func unlock(_ call: CAPPluginCall) {
        guard let id = gcId(call.getString("id")) else { call.resolve(result(false)); return }
        report(id, percent: Double(call.getDouble("percent") ?? 100), call)
    }

    /// { id, steps, total } o { id, percent }
    @objc func progress(_ call: CAPPluginCall) {
        guard let id = gcId(call.getString("id")) else { call.resolve(result(false)); return }
        var pct = call.getDouble("percent")
        if pct == nil, let steps = call.getDouble("steps"), let total = call.getDouble("total"), total > 0 {
            pct = steps / total * 100
        }
        guard let p = pct, p > 0 else { call.resolve(result(false)); return }
        report(id, percent: p, call)
    }

    /// { board: "height", score: 412 } (tiempo en milisegundos)
    @objc func submitScore(_ call: CAPPluginCall) {
        guard let id = gcId(call.getString("board")),
              let score = call.getDouble("score") else { call.resolve(result(false)); return }
        guard GKLocalPlayer.local.isAuthenticated else { call.resolve(result(false)); return }
        // El juego manda el tiempo en ms (como Android); Game Center lo guarda en centésimas.
        let value = (id == prefix + "time" || id.hasPrefix(prefix + "time_")) ? Int(score / 10) : Int(score)
        GKLeaderboard.submitScore(value, context: 0, player: GKLocalPlayer.local, leaderboardIDs: [id]) { error in
            call.resolve(self.result(error == nil, error.map { ["error": $0.localizedDescription] } ?? [:]))
        }
    }

    private func present(_ vc: GKGameCenterViewController, _ call: CAPPluginCall) {
        guard GKLocalPlayer.local.isAuthenticated else { call.resolve(result(false)); return }
        vc.gameCenterDelegate = self
        bridge?.viewController?.present(vc, animated: true)
        call.resolve(result(true))
    }

    /// Top N de un marcador más la posición del jugador. Resuelve { ok, entries:[{rank,score,name}], player:{rank,score,total}|null }.
    @objc func loadTop(_ call: CAPPluginCall) {
        guard let id = gcId(call.getString("board")) else { call.resolve(["ok": false, "entries": []]); return }
        guard GKLocalPlayer.local.isAuthenticated else { call.resolve(["ok": false, "signedIn": false, "entries": []]); return }
        let n = max(1, min(call.getInt("n") ?? 3, 100))
        GKLeaderboard.loadLeaderboards(IDs: [id]) { boards, error in
            guard let board = boards?.first, error == nil else {
                call.resolve(["ok": false, "entries": [], "error": error?.localizedDescription ?? "no board"]); return
            }
            board.loadEntries(for: .global, timeScope: .allTime, range: NSRange(location: 1, length: n)) { local, entries, total, error in
                if let error = error { call.resolve(["ok": false, "entries": [], "error": error.localizedDescription]); return }
                let list: [[String: Any]] = (entries ?? []).map { ["rank": $0.rank, "score": $0.score, "name": $0.player.displayName] }
                var res: [String: Any] = ["ok": true, "entries": list]
                if let l = local { res["player"] = ["rank": l.rank, "score": l.score, "total": total] }
                else { res["player"] = NSNull() }
                call.resolve(res)
            }
        }
    }

    /// PRUEBAS: borra el progreso de todos los logros de este jugador en Game Center.
    @objc func resetAchievements(_ call: CAPPluginCall) {
        guard GKLocalPlayer.local.isAuthenticated else { call.resolve(["ok": false, "signedIn": false]); return }
        GKAchievement.resetAchievements { error in
            if let error = error { call.reject(error.localizedDescription) }
            else { call.resolve(["ok": true, "signedIn": true]) }
        }
    }

    @objc func showAchievements(_ call: CAPPluginCall) {
        DispatchQueue.main.async { self.present(GKGameCenterViewController(state: .achievements), call) }
    }

    /// { board: "height" } o sin board para ver todos
    @objc func showLeaderboard(_ call: CAPPluginCall) {
        let id = gcId(call.getString("board"))
        DispatchQueue.main.async {
            let vc = id.map { GKGameCenterViewController(leaderboardID: $0, playerScope: .global, timeScope: .allTime) }
                ?? GKGameCenterViewController(state: .leaderboards)
            self.present(vc, call)
        }
    }

    public func gameCenterViewControllerDidFinish(_ gameCenterViewController: GKGameCenterViewController) {
        gameCenterViewController.dismiss(animated: true)
    }
}

/// Escucha cuando el jugador abre un reto o actividad de Game Center (app Juegos de iOS 26).
@available(iOS 26.0, *)
private final class OmfActivityListener: NSObject, GKLocalPlayerListener {
    weak var plugin: GameCenterPlugin?
    init(plugin: GameCenterPlugin) { self.plugin = plugin }

    func player(_ player: GKPlayer, wantsToPlay activity: GKGameActivity) async -> Bool {
        let id = activity.activityDefinition.identifier
        let party = activity.partyCode ?? ""
        await MainActor.run { self.plugin?.gotActivity(id: id, party: party) }
        return true
    }
}
