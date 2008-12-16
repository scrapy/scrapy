def setup(app):
    app.add_description_unit(
        directivename = "setting",
        rolename      = "setting",
        indextemplate = "pair: %s; setting",
    )
