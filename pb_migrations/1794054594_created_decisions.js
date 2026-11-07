/// <reference path="../pb_data/types.d.ts" />
migrate((app) => {
  const collection = new Collection({
    "createRule": "@request.auth.id != '' && @request.body.user = @request.auth.id",
    "deleteRule": "user = @request.auth.id",
    "fields": [
      {
        "autogeneratePattern": "[a-z0-9]{15}",
        "help": "",
        "hidden": false,
        "id": "text3208210256",
        "max": 15,
        "min": 15,
        "name": "id",
        "pattern": "^[a-z0-9]+$",
        "presentable": false,
        "primaryKey": true,
        "required": true,
        "system": true,
        "type": "text"
      },
      {
        "cascadeDelete": false,
        "collectionId": "_pb_users_auth_",
        "help": "",
        "hidden": false,
        "id": "relation2375276105",
        "maxSelect": 1,
        "minSelect": 0,
        "name": "user",
        "presentable": false,
        "required": true,
        "system": false,
        "type": "relation"
      },
      {
        "autogeneratePattern": "",
        "help": "",
        "hidden": false,
        "id": "text82164196",
        "max": 20,
        "min": 0,
        "name": "asset_symbol",
        "pattern": "",
        "presentable": false,
        "primaryKey": false,
        "required": true,
        "system": false,
        "type": "text"
      },
      {
        "help": "",
        "hidden": false,
        "id": "select1204587666",
        "maxSelect": 1,
        "name": "action",
        "presentable": false,
        "required": true,
        "system": false,
        "type": "select",
        "values": [
          "BUY",
          "SELL",
          "HOLD"
        ]
      },
      {
        "help": "",
        "hidden": false,
        "id": "select1131609387",
        "maxSelect": 1,
        "name": "sentiment",
        "presentable": false,
        "required": true,
        "system": false,
        "type": "select",
        "values": [
          "FOMO",
          "STRATEGIC",
          "PANIC",
          "DIVIDEND",
          "OPPORTUNITY"
        ]
      },
      {
        "autogeneratePattern": "",
        "help": "",
        "hidden": false,
        "id": "text1860142517",
        "max": 5000,
        "min": 0,
        "name": "rationale",
        "pattern": "",
        "presentable": false,
        "primaryKey": false,
        "required": false,
        "system": false,
        "type": "text"
      },
      {
        "help": "",
        "hidden": false,
        "id": "number1986247125",
        "max": null,
        "min": 0,
        "name": "target_price",
        "onlyInt": false,
        "presentable": false,
        "required": false,
        "system": false,
        "type": "number"
      },
      {
        "help": "",
        "hidden": false,
        "id": "date1736843723",
        "max": "",
        "min": "",
        "name": "target_date",
        "presentable": false,
        "required": false,
        "system": false,
        "type": "date"
      },
      {
        "help": "",
        "hidden": false,
        "id": "select2063623452",
        "maxSelect": 1,
        "name": "status",
        "presentable": false,
        "required": true,
        "system": false,
        "type": "select",
        "values": [
          "OPEN",
          "EXPIRED",
          "REVIEWED",
          "CLOSED"
        ]
      },
      {
        "autogeneratePattern": "",
        "help": "",
        "hidden": false,
        "id": "text3296709437",
        "max": 0,
        "min": 0,
        "name": "ai_retrospective",
        "pattern": "",
        "presentable": false,
        "primaryKey": false,
        "required": false,
        "system": false,
        "type": "text"
      },
      {
        "help": "",
        "hidden": false,
        "id": "number3125644320",
        "max": null,
        "min": null,
        "name": "outcome_return_pct",
        "onlyInt": false,
        "presentable": false,
        "required": false,
        "system": false,
        "type": "number"
      },
      {
        "help": "",
        "hidden": false,
        "id": "date3977810955",
        "max": "",
        "min": "",
        "name": "decision_date",
        "presentable": false,
        "required": false,
        "system": false,
        "type": "date"
      },
      {
        "help": "",
        "hidden": false,
        "id": "number247322292",
        "max": null,
        "min": null,
        "name": "outcome_price",
        "onlyInt": false,
        "presentable": false,
        "required": false,
        "system": false,
        "type": "number"
      },
      {
        "help": "",
        "hidden": false,
        "id": "bool2512520372",
        "name": "target_hit",
        "presentable": false,
        "required": false,
        "system": false,
        "type": "bool"
      },
      {
        "cascadeDelete": false,
        "collectionId": "pbc_3174063690",
        "help": "",
        "hidden": false,
        "id": "relation1916208593",
        "maxSelect": 1,
        "minSelect": 0,
        "name": "transaction",
        "presentable": false,
        "required": false,
        "system": false,
        "type": "relation"
      }
    ],
    "id": "pbc_128339087",
    "indexes": [],
    "listRule": "user = @request.auth.id",
    "name": "decisions",
    "system": false,
    "type": "base",
    "updateRule": "user = @request.auth.id && @request.body.user:isset = false",
    "viewRule": "user = @request.auth.id"
  });

  return app.save(collection);
}, (app) => {
  const collection = app.findCollectionByNameOrId("pbc_128339087");

  return app.delete(collection);
})
