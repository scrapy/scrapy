from scrapy.item import Field, Item, ItemMeta


class DjangoItemMeta(ItemMeta):

    def  __new__(mcs, class_name, bases, attrs):
        cls = super(DjangoItemMeta, mcs).__new__(mcs, class_name, bases, attrs)
        cls.fields = cls.fields.copy()

        if cls.django_model:
            cls._model_fields = []
            cls._model_meta = cls.django_model._meta
            for model_field in cls._model_meta.fields:
                if model_field.auto_created == False:
                    if model_field.name not in cls.fields:
                        cls.fields[model_field.name] = Field()
                    cls._model_fields.append(model_field.name)
        return cls


class DjangoItem(Item):

    __metaclass__ = DjangoItemMeta

    django_model = None

    def save(self, commit=True):
        modelargs = dict((k, self.get(k)) for k in self._values
                         if k in self._model_fields)
        model = self.django_model(**modelargs)
        if commit:
            model.save()
        return model
