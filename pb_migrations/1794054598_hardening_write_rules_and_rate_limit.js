/// <reference path="../pb_data/types.d.ts" />

// P3: Yazma kurallarını null yap (kullanıcı PB'den doğrudan create/update/delete yapamaz)
// Sadece FastAPI admin client üzerinden yazılabilir.
// Ayrıca rate limiter'ı etkinleştir.

migrate(
    (app) => {
        // transactions
        const transactions = app.findCollectionByNameOrId("transactions")
        transactions.createRule = null
        transactions.updateRule = null
        transactions.deleteRule = null
        app.save(transactions)

        // decisions
        const decisions = app.findCollectionByNameOrId("decisions")
        decisions.createRule = null
        decisions.updateRule = null
        decisions.deleteRule = null
        app.save(decisions)

        // shadow_portfolios
        const shadow = app.findCollectionByNameOrId("shadow_portfolios")
        shadow.createRule = null
        shadow.updateRule = null
        shadow.deleteRule = null
        app.save(shadow)

        // Rate limiter etkinleştir
        const settings = app.settings()
        settings.rateLimits.enabled = true
        // Auth endpoint'leri için varsayılan limitler yeterli; istenirse özelleştirilebilir
        app.save(settings)
    },
    (app) => {
        // Rollback: varsayılan kullanıcı yazma kurallarına dön (gerekirse)
        const transactions = app.findCollectionByNameOrId("transactions")
        transactions.createRule = "@request.auth.id != '' && @request.body.user = @request.auth.id"
        transactions.updateRule = "user = @request.auth.id && @request.body.user:isset = false"
        transactions.deleteRule = "user = @request.auth.id"
        app.save(transactions)

        const decisions = app.findCollectionByNameOrId("decisions")
        decisions.createRule = "@request.auth.id != '' && @request.body.user = @request.auth.id"
        decisions.updateRule = "user = @request.auth.id && @request.body.user:isset = false"
        decisions.deleteRule = "user = @request.auth.id"
        app.save(decisions)

        const shadow = app.findCollectionByNameOrId("shadow_portfolios")
        shadow.createRule = "@request.auth.id != '' && @request.body.user = @request.auth.id"
        shadow.updateRule = "user = @request.auth.id && @request.body.user:isset = false"
        shadow.deleteRule = "user = @request.auth.id"
        app.save(shadow)

        const settings = app.settings()
        settings.rateLimits.enabled = false
        app.save(settings)
    }
)