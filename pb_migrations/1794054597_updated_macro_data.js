/// <reference path="../pb_data/types.d.ts" />

// e2e denetimi: benchmark_service._upsert_to_pb `source` ve `is_estimate` yazıyor
// ama şemada yoklardı — PB bu alanları sessizce düşürüyordu (gold_try_gram vakasının
// aynı sınıfı). Kaynak/izin-provenance'ı artık kalıcı.
migrate(
    (app) => {
        const collection = app.findCollectionByNameOrId("pbc_2566843761")

        collection.fields.add(new TextField({ name: "source", presentable: false }))
        collection.fields.add(new BoolField({ name: "is_estimate", presentable: false }))

        return app.save(collection)
    },
    (app) => {
        const collection = app.findCollectionByNameOrId("pbc_2566843761")

        collection.fields.removeByName("source")
        collection.fields.removeByName("is_estimate")

        return app.save(collection)
    }
)
