/// <reference path="../pb_data/types.d.ts" />

// P11: macro_data.gold_try → gold_try_gram
// Kod tabanı (benchmark_service) 14 noktada gold_try_gram alanını okuyup yazıyor;
// şemadaki eski gold_try adı nedeniyle PB bu alanı sessizce düşürüyordu.
// PB 0.40 JS API'sinde koleksiyon alanları collection.fields üzerinden erişilir.
migrate(
    (app) => {
        const collection = app.findCollectionByNameOrId("macro_data")
        const fields = collection.fields

        for (const f of fields) {
            if (f.name === "gold_try") {
                f.name = "gold_try_gram"
            }
        }

        app.save(collection)
    },
    (app) => {
        const collection = app.findCollectionByNameOrId("macro_data")
        const fields = collection.fields

        for (const f of fields) {
            if (f.name === "gold_try_gram") {
                f.name = "gold_try"
            }
        }

        app.save(collection)
    }
)
