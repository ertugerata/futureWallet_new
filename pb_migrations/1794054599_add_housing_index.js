/// <reference path="../pb_data/types.d.ts" />

// P7: housing_index alanı ekleniyor (EVDS konut fiyat endeksi için)

migrate(
    (app) => {
        const collection = app.findCollectionByNameOrId("macro_data")

        collection.fields.add(new TextField({ 
            name: "housing_index", 
            presentable: false,
            min: 0,
            pattern: "",
            max: 0,
            required: false
        }))

        return app.save(collection)
    },
    (app) => {
        const collection = app.findCollectionByNameOrId("macro_data")

        collection.fields.removeByName("housing_index")

        return app.save(collection)
    }
)