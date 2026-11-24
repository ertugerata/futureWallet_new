/// <reference path="../pb_data/types.d.ts" />

// P5-6: housing_index TextField -> NumberField migration
// Schema-only migration. Data copy should be handled separately.

migrate(
    (app) => {
        const collection = app.findCollectionByNameOrId("macro_data")

        // 1. Rename existing text field to housing_index_old
        const oldField = collection.fields.getByName("housing_index")
        if (oldField) {
            oldField.name = "housing_index_old"
            collection.fields.removeByName("housing_index")
            collection.fields.add(oldField)
        }

        // 2. Add new number field housing_index
        collection.fields.add(new NumberField({
            name: "housing_index",
            presentable: false,
            min: 0,
            required: false,
        }))

        return app.save(collection)
    },
    (app) => {
        const collection = app.findCollectionByNameOrId("macro_data")

        // Reverse: remove number field, rename old back
        collection.fields.removeByName("housing_index")

        const oldField = collection.fields.getByName("housing_index_old")
        if (oldField) {
            oldField.name = "housing_index"
            collection.fields.removeByName("housing_index_old")
            collection.fields.add(oldField)
        }

        return app.save(collection)
    }
)