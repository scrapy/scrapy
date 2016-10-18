/*###########################################################################
 #
 # Copyright (c) 2003 Zope Foundation and Contributors.
 # All Rights Reserved.
 #
 # This software is subject to the provisions of the Zope Public License,
 # Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
 # THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
 # WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
 # WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
 # FOR A PARTICULAR PURPOSE.
 #
 ############################################################################*/

#include "Python.h"
#include "structmember.h"

#define TYPE(O) ((PyTypeObject*)(O))
#define OBJECT(O) ((PyObject*)(O))
#define CLASSIC(O) ((PyClassObject*)(O))
#ifndef PyVarObject_HEAD_INIT
#define PyVarObject_HEAD_INIT(a, b) PyObject_HEAD_INIT(a) b,
#endif
#ifndef Py_TYPE
#define Py_TYPE(o) ((o)->ob_type)
#endif

static PyObject *str__dict__, *str__implemented__, *strextends;
static PyObject *BuiltinImplementationSpecifications, *str__provides__;
static PyObject *str__class__, *str__providedBy__;
static PyObject *empty, *fallback, *str_implied, *str_cls, *str_implements;
static PyObject *str__conform__, *str_call_conform, *adapter_hooks;
static PyObject *str_uncached_lookup, *str_uncached_lookupAll;
static PyObject *str_uncached_subscriptions;
static PyObject *str_registry, *strro, *str_generation, *strchanged;

static PyTypeObject *Implements;

static int imported_declarations = 0;

static int 
import_declarations(void)
{
  PyObject *declarations, *i;

  declarations = PyImport_ImportModule("zope.interface.declarations");
  if (declarations == NULL)
    return -1;
  
  BuiltinImplementationSpecifications = PyObject_GetAttrString(
                    declarations, "BuiltinImplementationSpecifications");
  if (BuiltinImplementationSpecifications == NULL)
    return -1;

  empty = PyObject_GetAttrString(declarations, "_empty");
  if (empty == NULL)
    return -1;

  fallback = PyObject_GetAttrString(declarations, "implementedByFallback");
  if (fallback == NULL)
    return -1;



  i = PyObject_GetAttrString(declarations, "Implements");
  if (i == NULL)
    return -1;

  if (! PyType_Check(i))
    {
      PyErr_SetString(PyExc_TypeError, 
                      "zope.interface.declarations.Implements is not a type");
      return -1;
    }

  Implements = (PyTypeObject *)i;

  Py_DECREF(declarations);

  imported_declarations = 1;
  return 0;
}

static PyTypeObject SpecType;   /* Forward */

static PyObject *
implementedByFallback(PyObject *cls)
{
  if (imported_declarations == 0 && import_declarations() < 0)
    return NULL;

  return PyObject_CallFunctionObjArgs(fallback, cls, NULL);
}

static PyObject *
implementedBy(PyObject *ignored, PyObject *cls)
{
  /* Fast retrieval of implements spec, if possible, to optimize
     common case.  Use fallback code if we get stuck.
  */

  PyObject *dict = NULL, *spec;

  if (PyType_Check(cls))
    {
      dict = TYPE(cls)->tp_dict;
      Py_XINCREF(dict);
    }

  if (dict == NULL)
    dict = PyObject_GetAttr(cls, str__dict__);

  if (dict == NULL)
    {
      /* Probably a security proxied class, use more expensive fallback code */
      PyErr_Clear();
      return implementedByFallback(cls);
    }

  spec = PyObject_GetItem(dict, str__implemented__);
  Py_DECREF(dict);
  if (spec)
    {
      if (imported_declarations == 0 && import_declarations() < 0)
        return NULL;

      if (PyObject_TypeCheck(spec, Implements))
        return spec;

      /* Old-style declaration, use more expensive fallback code */
      Py_DECREF(spec);
      return implementedByFallback(cls);
    }

  PyErr_Clear();

  /* Maybe we have a builtin */
  if (imported_declarations == 0 && import_declarations() < 0)
    return NULL;
  
  spec = PyDict_GetItem(BuiltinImplementationSpecifications, cls);
  if (spec != NULL)
    {
      Py_INCREF(spec);
      return spec;
    }

  /* We're stuck, use fallback */
  return implementedByFallback(cls);
}

static PyObject *
getObjectSpecification(PyObject *ignored, PyObject *ob)
{
  PyObject *cls, *result;

  result = PyObject_GetAttr(ob, str__provides__);
  if (result != NULL && PyObject_TypeCheck(result, &SpecType))
    return result;

  PyErr_Clear();

  /* We do a getattr here so as not to be defeated by proxies */
  cls = PyObject_GetAttr(ob, str__class__);
  if (cls == NULL)
    {
      PyErr_Clear();
      if (imported_declarations == 0 && import_declarations() < 0)
        return NULL;
      Py_INCREF(empty);
      return empty;
    }

  result = implementedBy(NULL, cls);
  Py_DECREF(cls);

  return result;
}

static PyObject *
providedBy(PyObject *ignored, PyObject *ob)
{
  PyObject *result, *cls, *cp;
  
  result = PyObject_GetAttr(ob, str__providedBy__);
  if (result == NULL)
    {
      PyErr_Clear();
      return getObjectSpecification(NULL, ob);
    } 


  /* We want to make sure we have a spec. We can't do a type check
     because we may have a proxy, so we'll just try to get the
     only attribute.
  */
  if (PyObject_TypeCheck(result, &SpecType)
      || 
      PyObject_HasAttr(result, strextends)
      )
    return result;
    
  /*
    The object's class doesn't understand descriptors.
    Sigh. We need to get an object descriptor, but we have to be
    careful.  We want to use the instance's __provides__,l if
    there is one, but only if it didn't come from the class.
  */
  Py_DECREF(result);

  cls = PyObject_GetAttr(ob, str__class__);
  if (cls == NULL)
    return NULL;

  result = PyObject_GetAttr(ob, str__provides__);
  if (result == NULL)
    {      
      /* No __provides__, so just fall back to implementedBy */
      PyErr_Clear();
      result = implementedBy(NULL, cls);
      Py_DECREF(cls);
      return result;
    } 

  cp = PyObject_GetAttr(cls, str__provides__);
  if (cp == NULL)
    {
      /* The the class has no provides, assume we're done: */
      PyErr_Clear();
      Py_DECREF(cls);
      return result;
    }

  if (cp == result)
    {
      /*
        Oops, we got the provides from the class. This means
        the object doesn't have it's own. We should use implementedBy
      */
      Py_DECREF(result);
      result = implementedBy(NULL, cls);
    }

  Py_DECREF(cls);
  Py_DECREF(cp);

  return result;
}

/* 
   Get an attribute from an inst dict. Return a borrowed reference.
  
   This has a number of advantages:

   - It avoids layers of Python api

   - It doesn't waste time looking for descriptors

   - It fails wo raising an exception, although that shouldn't really
     matter.

*/
static PyObject *
inst_attr(PyObject *self, PyObject *name)
{
  PyObject **dictp, *v;

  dictp = _PyObject_GetDictPtr(self);
  if (dictp && *dictp && (v = PyDict_GetItem(*dictp, name)))
    return v;
  PyErr_SetObject(PyExc_AttributeError, name);
  return NULL;
}


static PyObject *
Spec_extends(PyObject *self, PyObject *other)
{  
  PyObject *implied;

  implied = inst_attr(self, str_implied);
  if (implied == NULL)
    return NULL;

#ifdef Py_True
  if (PyDict_GetItem(implied, other) != NULL)
    {
      Py_INCREF(Py_True);
      return Py_True;
    }
  Py_INCREF(Py_False);
  return Py_False;
#else
  return PyInt_FromLong(PyDict_GetItem(implied, other) != NULL);
#endif
}

static char Spec_extends__doc__[] = 
"Test whether a specification is or extends another"
;

static char Spec_providedBy__doc__[] = 
"Test whether an interface is implemented by the specification"
;

static PyObject *
Spec_call(PyObject *self, PyObject *args, PyObject *kw)
{
  PyObject *spec;

  if (! PyArg_ParseTuple(args, "O", &spec))
    return NULL;
  return Spec_extends(self, spec);
}

static PyObject *
Spec_providedBy(PyObject *self, PyObject *ob)
{
  PyObject *decl, *item;

  decl = providedBy(NULL, ob);
  if (decl == NULL)
    return NULL;

  if (PyObject_TypeCheck(decl, &SpecType))
    item = Spec_extends(decl, self);
  else
    /* decl is probably a security proxy.  We have to go the long way
       around. 
    */
    item = PyObject_CallFunctionObjArgs(decl, self, NULL);

  Py_DECREF(decl);
  return item;
}


static char Spec_implementedBy__doc__[] = 
"Test whether the specification is implemented by a class or factory.\n"
"Raise TypeError if argument is neither a class nor a callable."
;

static PyObject *
Spec_implementedBy(PyObject *self, PyObject *cls)
{
  PyObject *decl, *item;

  decl = implementedBy(NULL, cls);
  if (decl == NULL)
    return NULL;
  
  if (PyObject_TypeCheck(decl, &SpecType))
    item = Spec_extends(decl, self);
  else
    item = PyObject_CallFunctionObjArgs(decl, self, NULL);

  Py_DECREF(decl);
  return item;
}

static struct PyMethodDef Spec_methods[] = {
	{"providedBy",  
         (PyCFunction)Spec_providedBy,		METH_O,
	 Spec_providedBy__doc__},
	{"implementedBy", 
         (PyCFunction)Spec_implementedBy,	METH_O,
	 Spec_implementedBy__doc__},
	{"isOrExtends",	(PyCFunction)Spec_extends,	METH_O,
	 Spec_extends__doc__},

	{NULL,		NULL}		/* sentinel */
};

static PyTypeObject SpecType = {
	PyVarObject_HEAD_INIT(NULL, 0)
	/* tp_name           */ "_interface_coptimizations."
                                "SpecificationBase",
	/* tp_basicsize      */ 0,
	/* tp_itemsize       */ 0,
	/* tp_dealloc        */ (destructor)0,
	/* tp_print          */ (printfunc)0,
	/* tp_getattr        */ (getattrfunc)0,
	/* tp_setattr        */ (setattrfunc)0,
	/* tp_compare        */ 0,
	/* tp_repr           */ (reprfunc)0,
	/* tp_as_number      */ 0,
	/* tp_as_sequence    */ 0,
	/* tp_as_mapping     */ 0,
	/* tp_hash           */ (hashfunc)0,
	/* tp_call           */ (ternaryfunc)Spec_call,
	/* tp_str            */ (reprfunc)0,
        /* tp_getattro       */ (getattrofunc)0,
        /* tp_setattro       */ (setattrofunc)0,
        /* tp_as_buffer      */ 0,
        /* tp_flags          */ Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
        "Base type for Specification objects",
        /* tp_traverse       */ (traverseproc)0,
        /* tp_clear          */ (inquiry)0,
        /* tp_richcompare    */ (richcmpfunc)0,
        /* tp_weaklistoffset */ (long)0,
        /* tp_iter           */ (getiterfunc)0,
        /* tp_iternext       */ (iternextfunc)0,
        /* tp_methods        */ Spec_methods,
};

static PyObject *
OSD_descr_get(PyObject *self, PyObject *inst, PyObject *cls)
{
  PyObject *provides;

  if (inst == NULL)
    return getObjectSpecification(NULL, cls);

  provides = PyObject_GetAttr(inst, str__provides__);
  if (provides != NULL)
    return provides;
  PyErr_Clear();
  return implementedBy(NULL, cls);
}

static PyTypeObject OSDType = {
	PyVarObject_HEAD_INIT(NULL, 0)
	/* tp_name           */ "_interface_coptimizations."
                                "ObjectSpecificationDescriptor",
	/* tp_basicsize      */ 0,
	/* tp_itemsize       */ 0,
	/* tp_dealloc        */ (destructor)0,
	/* tp_print          */ (printfunc)0,
	/* tp_getattr        */ (getattrfunc)0,
	/* tp_setattr        */ (setattrfunc)0,
	/* tp_compare        */ 0,
	/* tp_repr           */ (reprfunc)0,
	/* tp_as_number      */ 0,
	/* tp_as_sequence    */ 0,
	/* tp_as_mapping     */ 0,
	/* tp_hash           */ (hashfunc)0,
	/* tp_call           */ (ternaryfunc)0,
	/* tp_str            */ (reprfunc)0,
        /* tp_getattro       */ (getattrofunc)0,
        /* tp_setattro       */ (setattrofunc)0,
        /* tp_as_buffer      */ 0,
        /* tp_flags          */ Py_TPFLAGS_DEFAULT
				| Py_TPFLAGS_BASETYPE ,
	"Object Specification Descriptor",
        /* tp_traverse       */ (traverseproc)0,
        /* tp_clear          */ (inquiry)0,
        /* tp_richcompare    */ (richcmpfunc)0,
        /* tp_weaklistoffset */ (long)0,
        /* tp_iter           */ (getiterfunc)0,
        /* tp_iternext       */ (iternextfunc)0,
        /* tp_methods        */ 0,
        /* tp_members        */ 0,
        /* tp_getset         */ 0,
        /* tp_base           */ 0,
        /* tp_dict           */ 0, /* internal use */
        /* tp_descr_get      */ (descrgetfunc)OSD_descr_get,
};

static PyObject *
CPB_descr_get(PyObject *self, PyObject *inst, PyObject *cls)
{
  PyObject *mycls, *implements;

  mycls = inst_attr(self, str_cls);
  if (mycls == NULL)
    return NULL;

  if (cls == mycls)
    {
      if (inst == NULL)
        {
          Py_INCREF(self);
          return OBJECT(self);
        }

      implements = inst_attr(self, str_implements);
      Py_XINCREF(implements);
      return implements;
    }
  
  PyErr_SetObject(PyExc_AttributeError, str__provides__);
  return NULL;
}

static PyTypeObject CPBType = {
	PyVarObject_HEAD_INIT(NULL, 0)
	/* tp_name           */ "_interface_coptimizations."
                                "ClassProvidesBase",
	/* tp_basicsize      */ 0,
	/* tp_itemsize       */ 0,
	/* tp_dealloc        */ (destructor)0,
	/* tp_print          */ (printfunc)0,
	/* tp_getattr        */ (getattrfunc)0,
	/* tp_setattr        */ (setattrfunc)0,
	/* tp_compare        */ 0,
	/* tp_repr           */ (reprfunc)0,
	/* tp_as_number      */ 0,
	/* tp_as_sequence    */ 0,
	/* tp_as_mapping     */ 0,
	/* tp_hash           */ (hashfunc)0,
	/* tp_call           */ (ternaryfunc)0,
	/* tp_str            */ (reprfunc)0,
        /* tp_getattro       */ (getattrofunc)0,
        /* tp_setattro       */ (setattrofunc)0,
        /* tp_as_buffer      */ 0,
        /* tp_flags          */ Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
        "C Base class for ClassProvides",
        /* tp_traverse       */ (traverseproc)0,
        /* tp_clear          */ (inquiry)0,
        /* tp_richcompare    */ (richcmpfunc)0,
        /* tp_weaklistoffset */ (long)0,
        /* tp_iter           */ (getiterfunc)0,
        /* tp_iternext       */ (iternextfunc)0,
        /* tp_methods        */ 0,
        /* tp_members        */ 0,
        /* tp_getset         */ 0,
        /* tp_base           */ &SpecType,
        /* tp_dict           */ 0, /* internal use */
        /* tp_descr_get      */ (descrgetfunc)CPB_descr_get,
};

/* ==================================================================== */
/* ========== Begin: __call__ and __adapt__ =========================== */

/*
    def __adapt__(self, obj):
        """Adapt an object to the reciever
        """
        if self.providedBy(obj):
            return obj

        for hook in adapter_hooks:
            adapter = hook(self, obj)
            if adapter is not None:
                return adapter

  
*/
static PyObject *
__adapt__(PyObject *self, PyObject *obj)
{
  PyObject *decl, *args, *adapter;
  int implements, i, l;

  decl = providedBy(NULL, obj);
  if (decl == NULL)
    return NULL;

  if (PyObject_TypeCheck(decl, &SpecType))
    {
      PyObject *implied;

      implied = inst_attr(decl, str_implied);
      if (implied == NULL)
        {
          Py_DECREF(decl);
          return NULL;
        }

      implements = PyDict_GetItem(implied, self) != NULL;
      Py_DECREF(decl);
    }
  else
    {
      /* decl is probably a security proxy.  We have to go the long way
         around. 
      */
      PyObject *r;
      r = PyObject_CallFunctionObjArgs(decl, self, NULL);
      Py_DECREF(decl);
      if (r == NULL)
        return NULL;
      implements = PyObject_IsTrue(r);
      Py_DECREF(r);
    }

  if (implements)
    {
      Py_INCREF(obj);
      return obj;
    }

  l = PyList_GET_SIZE(adapter_hooks);
  args = PyTuple_New(2);
  if (args == NULL)
    return NULL;
  Py_INCREF(self);
  PyTuple_SET_ITEM(args, 0, self);
  Py_INCREF(obj);
  PyTuple_SET_ITEM(args, 1, obj);
  for (i = 0; i < l; i++)
    {
      adapter = PyObject_CallObject(PyList_GET_ITEM(adapter_hooks, i), args);
      if (adapter == NULL || adapter != Py_None)
        {
          Py_DECREF(args);
          return adapter;
        }
      Py_DECREF(adapter);
    }

  Py_DECREF(args);

  Py_INCREF(Py_None);
  return Py_None;
}

static struct PyMethodDef ib_methods[] = {
  {"__adapt__",	(PyCFunction)__adapt__, METH_O,
   "Adapt an object to the reciever"},
  {NULL,		NULL}		/* sentinel */
};

/* 
        def __call__(self, obj, alternate=_marker):
            conform = getattr(obj, '__conform__', None)
            if conform is not None:
                adapter = self._call_conform(conform)
                if adapter is not None:
                    return adapter

            adapter = self.__adapt__(obj)

            if adapter is not None:
                return adapter
            elif alternate is not _marker:
                return alternate
            else:
                raise TypeError("Could not adapt", obj, self)
*/
static PyObject *
ib_call(PyObject *self, PyObject *args, PyObject *kwargs)
{
  PyObject *conform, *obj, *alternate=NULL, *adapter;
  
  static char *kwlist[] = {"obj", "alternate", NULL};

  if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|O", kwlist,
                                   &obj, &alternate))
    return NULL;

  conform = PyObject_GetAttr(obj, str__conform__);
  if (conform != NULL)
    {
      adapter = PyObject_CallMethodObjArgs(self, str_call_conform,
                                           conform, NULL);
      Py_DECREF(conform);
      if (adapter == NULL || adapter != Py_None)
        return adapter;
      Py_DECREF(adapter);
    }
  else
    PyErr_Clear();
 
  adapter = __adapt__(self, obj);
  if (adapter == NULL || adapter != Py_None)
    return adapter;
  Py_DECREF(adapter);

  if (alternate != NULL)
    {
      Py_INCREF(alternate);
      return alternate;
    }

  adapter = Py_BuildValue("sOO", "Could not adapt", obj, self);
  if (adapter != NULL)
    {
      PyErr_SetObject(PyExc_TypeError, adapter);
      Py_DECREF(adapter);
    }
  return NULL;
}

static PyTypeObject InterfaceBase = {
	PyVarObject_HEAD_INIT(NULL, 0)
	/* tp_name           */ "_zope_interface_coptimizations."
                                "InterfaceBase",
	/* tp_basicsize      */ 0,
	/* tp_itemsize       */ 0,
	/* tp_dealloc        */ (destructor)0,
	/* tp_print          */ (printfunc)0,
	/* tp_getattr        */ (getattrfunc)0,
	/* tp_setattr        */ (setattrfunc)0,
	/* tp_compare        */ 0,
	/* tp_repr           */ (reprfunc)0,
	/* tp_as_number      */ 0,
	/* tp_as_sequence    */ 0,
	/* tp_as_mapping     */ 0,
	/* tp_hash           */ (hashfunc)0,
	/* tp_call           */ (ternaryfunc)ib_call,
	/* tp_str            */ (reprfunc)0,
        /* tp_getattro       */ (getattrofunc)0,
        /* tp_setattro       */ (setattrofunc)0,
        /* tp_as_buffer      */ 0,
        /* tp_flags          */ Py_TPFLAGS_DEFAULT
				| Py_TPFLAGS_BASETYPE ,
	/* tp_doc */ "Interface base type providing __call__ and __adapt__",
        /* tp_traverse       */ (traverseproc)0,
        /* tp_clear          */ (inquiry)0,
        /* tp_richcompare    */ (richcmpfunc)0,
        /* tp_weaklistoffset */ (long)0,
        /* tp_iter           */ (getiterfunc)0,
        /* tp_iternext       */ (iternextfunc)0,
        /* tp_methods        */ ib_methods,
};

/* =================== End: __call__ and __adapt__ ==================== */
/* ==================================================================== */

/* ==================================================================== */
/* ========================== Begin: Lookup Bases ===================== */

typedef struct {
  PyObject_HEAD
  PyObject *_cache;
  PyObject *_mcache;
  PyObject *_scache;
} lookup;

typedef struct {
  PyObject_HEAD
  PyObject *_cache;
  PyObject *_mcache;
  PyObject *_scache;
  PyObject *_verify_ro;
  PyObject *_verify_generations;
} verify;

static int
lookup_traverse(lookup *self, visitproc visit, void *arg)
{
  int vret;

  if (self->_cache) {
    vret = visit(self->_cache, arg);
    if (vret != 0)
      return vret;
  }

  if (self->_mcache) {
    vret = visit(self->_mcache, arg);
    if (vret != 0)
      return vret;
  }

  if (self->_scache) {
    vret = visit(self->_scache, arg);
    if (vret != 0)
      return vret;
  }
  
  return 0;
}

static int
lookup_clear(lookup *self)
{
  Py_CLEAR(self->_cache);
  Py_CLEAR(self->_mcache);
  Py_CLEAR(self->_scache);
  return 0;
}

static void
lookup_dealloc(lookup *self)
{
  lookup_clear(self);
  Py_TYPE(self)->tp_free((PyObject*)self);
}

/*
    def changed(self, ignored=None):
        self._cache.clear()
        self._mcache.clear()
        self._scache.clear()
*/
static PyObject *
lookup_changed(lookup *self, PyObject *ignored)
{
  lookup_clear(self);
  Py_INCREF(Py_None);
  return Py_None;
}

#define ASSURE_DICT(N) if (N == NULL) { N = PyDict_New(); \
                                        if (N == NULL) return NULL; \
                                       }

/*  
    def _getcache(self, provided, name):
        cache = self._cache.get(provided)
        if cache is None:
            cache = {}
            self._cache[provided] = cache
        if name:
            c = cache.get(name)
            if c is None:
                c = {}
                cache[name] = c
            cache = c
        return cache
*/
static PyObject *
_subcache(PyObject *cache, PyObject *key)
{
  PyObject *subcache;

  subcache = PyDict_GetItem(cache, key);
  if (subcache == NULL)
    {
      int status;
 
      subcache = PyDict_New();
      if (subcache == NULL)
        return NULL;
      status = PyDict_SetItem(cache, key, subcache);
      Py_DECREF(subcache);
      if (status < 0)
        return NULL;
    }

  return subcache;
}
static PyObject *
_getcache(lookup *self, PyObject *provided, PyObject *name)
{
  PyObject *cache;

  ASSURE_DICT(self->_cache);
  cache = _subcache(self->_cache, provided);
  if (cache == NULL)
    return NULL;

  if (name != NULL && PyObject_IsTrue(name))
    cache = _subcache(cache, name);

  return cache;
}


/*  
    def lookup(self, required, provided, name=u'', default=None):
        cache = self._getcache(provided, name)
        if len(required) == 1:
            result = cache.get(required[0], _not_in_mapping)
        else:
            result = cache.get(tuple(required), _not_in_mapping)

        if result is _not_in_mapping:
            result = self._uncached_lookup(required, provided, name)
            if len(required) == 1:
                cache[required[0]] = result
            else:
                cache[tuple(required)] = result

        if result is None:
            return default

        return result
*/
static PyObject *
tuplefy(PyObject *v)
{
  if (! PyTuple_Check(v))
    {
      v = PyObject_CallFunctionObjArgs(OBJECT(&PyTuple_Type), v, NULL);
      if (v == NULL)
        return NULL;
    }
  else
    Py_INCREF(v);
  
  return v;
}
static PyObject *
_lookup(lookup *self, 
        PyObject *required, PyObject *provided, PyObject *name, 
        PyObject *default_)
{
  PyObject *result, *key, *cache;

  cache = _getcache(self, provided, name);
  if (cache == NULL)
    return NULL;

  required = tuplefy(required);
  if (required == NULL)
    return NULL;

  if (PyTuple_GET_SIZE(required) == 1)
    key = PyTuple_GET_ITEM(required, 0);
  else
    key = required;

  result = PyDict_GetItem(cache, key);
  if (result == NULL)
    {
      int status;

      result = PyObject_CallMethodObjArgs(OBJECT(self), str_uncached_lookup,
                                          required, provided, name, NULL);
      if (result == NULL)
        {
          Py_DECREF(required);
          return NULL;
        }
      status = PyDict_SetItem(cache, key, result);
      Py_DECREF(required);
      if (status < 0)
        {
          Py_DECREF(result);
          return NULL;
        }
    }
  else
    {
      Py_INCREF(result);
      Py_DECREF(required);
    }

  if (result == Py_None && default_ != NULL)
    {
      Py_DECREF(Py_None);
      Py_INCREF(default_);
      return default_;
    }

  return result;
}
static PyObject *
lookup_lookup(lookup *self, PyObject *args, PyObject *kwds)
{
  static char *kwlist[] = {"required", "provided", "name", "default", NULL};
  PyObject *required, *provided, *name=NULL, *default_=NULL;

  if (! PyArg_ParseTupleAndKeywords(args, kwds, "OO|OO", kwlist,
                                    &required, &provided, &name, &default_))
    return NULL; 

  return _lookup(self, required, provided, name, default_);
}


/*  
    def lookup1(self, required, provided, name=u'', default=None):
        cache = self._getcache(provided, name)
        result = cache.get(required, _not_in_mapping)
        if result is _not_in_mapping:
            return self.lookup((required, ), provided, name, default)

        if result is None:
            return default

        return result
*/
static PyObject *
_lookup1(lookup *self, 
        PyObject *required, PyObject *provided, PyObject *name, 
        PyObject *default_)
{
  PyObject *result, *cache;

  cache = _getcache(self, provided, name);
  if (cache == NULL)
    return NULL;

  result = PyDict_GetItem(cache, required);
  if (result == NULL)
    {
      PyObject *tup;

      tup = PyTuple_New(1);
      if (tup == NULL)
        return NULL;
      Py_INCREF(required);
      PyTuple_SET_ITEM(tup, 0, required);
      result = _lookup(self, tup, provided, name, default_);
      Py_DECREF(tup);
    }
  else
    {
      if (result == Py_None && default_ != NULL)
        {
          result = default_;
        }
      Py_INCREF(result);
    }

  return result;
}
static PyObject *
lookup_lookup1(lookup *self, PyObject *args, PyObject *kwds)
{
  static char *kwlist[] = {"required", "provided", "name", "default", NULL};
  PyObject *required, *provided, *name=NULL, *default_=NULL;

  if (! PyArg_ParseTupleAndKeywords(args, kwds, "OO|OO", kwlist,
                                    &required, &provided, &name, &default_))
    return NULL; 

  return _lookup1(self, required, provided, name, default_);
}

/*  
    def adapter_hook(self, provided, object, name=u'', default=None):
        required = providedBy(object)
        cache = self._getcache(provided, name)
        factory = cache.get(required, _not_in_mapping)
        if factory is _not_in_mapping:
            factory = self.lookup((required, ), provided, name)

        if factory is not None:
            result = factory(object)
            if result is not None:
                return result

        return default
*/
static PyObject *
_adapter_hook(lookup *self, 
              PyObject *provided, PyObject *object,  PyObject *name, 
              PyObject *default_)
{
  PyObject *required, *factory, *result;

  required = providedBy(NULL, object);
  if (required == NULL)
    return NULL;
  
  factory = _lookup1(self, required, provided, name, Py_None);
  Py_DECREF(required);
  if (factory == NULL)
    return NULL;
  
  if (factory != Py_None)
    {
      result = PyObject_CallFunctionObjArgs(factory, object, NULL);
      Py_DECREF(factory);
      if (result == NULL || result != Py_None)
        return result;
    }
  else
    result = factory; /* None */

  if (default_ == NULL || default_ == result) /* No default specified, */
    return result;   /* Return None.  result is owned None */

  Py_DECREF(result);
  Py_INCREF(default_);

  return default_;
}
static PyObject *
lookup_adapter_hook(lookup *self, PyObject *args, PyObject *kwds)
{
  static char *kwlist[] = {"provided", "object", "name", "default", NULL};
  PyObject *object, *provided, *name=NULL, *default_=NULL;

  if (! PyArg_ParseTupleAndKeywords(args, kwds, "OO|OO", kwlist,
                                    &provided, &object, &name, &default_))
    return NULL; 

  return _adapter_hook(self, provided, object, name, default_);
}

static PyObject *
lookup_queryAdapter(lookup *self, PyObject *args, PyObject *kwds)
{
  static char *kwlist[] = {"object", "provided", "name", "default", NULL};
  PyObject *object, *provided, *name=NULL, *default_=NULL;

  if (! PyArg_ParseTupleAndKeywords(args, kwds, "OO|OO", kwlist,
                                    &object, &provided, &name, &default_))
    return NULL; 

  return _adapter_hook(self, provided, object, name, default_);
}

/*  
    def lookupAll(self, required, provided):
        cache = self._mcache.get(provided)
        if cache is None:
            cache = {}
            self._mcache[provided] = cache

        required = tuple(required)
        result = cache.get(required, _not_in_mapping)
        if result is _not_in_mapping:
            result = self._uncached_lookupAll(required, provided)
            cache[required] = result

        return result
*/
static PyObject *
_lookupAll(lookup *self, PyObject *required, PyObject *provided)
{
  PyObject *cache, *result;

  ASSURE_DICT(self->_mcache);
  cache = _subcache(self->_mcache, provided);
  if (cache == NULL)
    return NULL;

  required = tuplefy(required);
  if (required == NULL)
    return NULL;

  result = PyDict_GetItem(cache, required);
  if (result == NULL)
    {
      int status;

      result = PyObject_CallMethodObjArgs(OBJECT(self), str_uncached_lookupAll,
                                          required, provided, NULL);
      if (result == NULL)
        {
          Py_DECREF(required);
          return NULL;
        }
      status = PyDict_SetItem(cache, required, result);
      Py_DECREF(required);
      if (status < 0)
        {
          Py_DECREF(result);
          return NULL;
        }
    }
  else
    {
      Py_INCREF(result);
      Py_DECREF(required);
    }

  return result;  
}
static PyObject *
lookup_lookupAll(lookup *self, PyObject *args, PyObject *kwds)
{
  static char *kwlist[] = {"required", "provided", NULL};
  PyObject *required, *provided;

  if (! PyArg_ParseTupleAndKeywords(args, kwds, "OO", kwlist,
                                    &required, &provided))
    return NULL; 

  return _lookupAll(self, required, provided);
}

/*  
    def subscriptions(self, required, provided):
        cache = self._scache.get(provided)
        if cache is None:
            cache = {}
            self._scache[provided] = cache

        required = tuple(required)
        result = cache.get(required, _not_in_mapping)
        if result is _not_in_mapping:
            result = self._uncached_subscriptions(required, provided)
            cache[required] = result

        return result
*/
static PyObject *
_subscriptions(lookup *self, PyObject *required, PyObject *provided)
{
  PyObject *cache, *result;

  ASSURE_DICT(self->_scache);
  cache = _subcache(self->_scache, provided);
  if (cache == NULL)
    return NULL;

  required = tuplefy(required);
  if (required == NULL)
    return NULL;

  result = PyDict_GetItem(cache, required);
  if (result == NULL)
    {
      int status;

      result = PyObject_CallMethodObjArgs(
                                 OBJECT(self), str_uncached_subscriptions,
                                 required, provided, NULL);
      if (result == NULL)
        {
          Py_DECREF(required);
          return NULL;
        }
      status = PyDict_SetItem(cache, required, result);
      Py_DECREF(required);
      if (status < 0)
        {
          Py_DECREF(result);
          return NULL;
        }
    }
  else
    {
      Py_INCREF(result);
      Py_DECREF(required);
    }

  return result;  
}
static PyObject *
lookup_subscriptions(lookup *self, PyObject *args, PyObject *kwds)
{
  static char *kwlist[] = {"required", "provided", NULL};
  PyObject *required, *provided;

  if (! PyArg_ParseTupleAndKeywords(args, kwds, "OO", kwlist,
                                    &required, &provided))
    return NULL; 

  return _subscriptions(self, required, provided);
}

static struct PyMethodDef lookup_methods[] = {
  {"changed",	    (PyCFunction)lookup_changed,       METH_O,        ""},
  {"lookup",	    (PyCFunction)lookup_lookup,	       METH_KEYWORDS, ""},
  {"lookup1",	    (PyCFunction)lookup_lookup1,       METH_KEYWORDS, ""},
  {"queryAdapter",  (PyCFunction)lookup_queryAdapter,  METH_KEYWORDS, ""},
  {"adapter_hook",  (PyCFunction)lookup_adapter_hook,  METH_KEYWORDS, ""},
  {"lookupAll",	    (PyCFunction)lookup_lookupAll,     METH_KEYWORDS, ""},
  {"subscriptions", (PyCFunction)lookup_subscriptions, METH_KEYWORDS, ""},
  {NULL,	    NULL}		/* sentinel */
};

static PyTypeObject LookupBase = {
	PyVarObject_HEAD_INIT(NULL, 0)
	/* tp_name           */ "_zope_interface_coptimizations."
                                "LookupBase",
	/* tp_basicsize      */ sizeof(lookup),
	/* tp_itemsize       */ 0,
	/* tp_dealloc        */ (destructor)&lookup_dealloc,
	/* tp_print          */ (printfunc)0,
	/* tp_getattr        */ (getattrfunc)0,
	/* tp_setattr        */ (setattrfunc)0,
	/* tp_compare        */ 0,
	/* tp_repr           */ (reprfunc)0,
	/* tp_as_number      */ 0,
	/* tp_as_sequence    */ 0,
	/* tp_as_mapping     */ 0,
	/* tp_hash           */ (hashfunc)0,
	/* tp_call           */ (ternaryfunc)0,
	/* tp_str            */ (reprfunc)0,
        /* tp_getattro       */ (getattrofunc)0,
        /* tp_setattro       */ (setattrofunc)0,
        /* tp_as_buffer      */ 0,
        /* tp_flags          */ Py_TPFLAGS_DEFAULT
				| Py_TPFLAGS_BASETYPE 
                          	| Py_TPFLAGS_HAVE_GC,
	/* tp_doc            */ "",
        /* tp_traverse       */ (traverseproc)lookup_traverse,
        /* tp_clear          */ (inquiry)lookup_clear,
        /* tp_richcompare    */ (richcmpfunc)0,
        /* tp_weaklistoffset */ (long)0,
        /* tp_iter           */ (getiterfunc)0,
        /* tp_iternext       */ (iternextfunc)0,
        /* tp_methods        */ lookup_methods,
};

static int
verifying_traverse(verify *self, visitproc visit, void *arg)
{
  int vret;

  vret = lookup_traverse((lookup *)self, visit, arg);
  if (vret != 0)
    return vret;

  if (self->_verify_ro) {
    vret = visit(self->_verify_ro, arg);
    if (vret != 0)
      return vret;
  }
  if (self->_verify_generations) {
    vret = visit(self->_verify_generations, arg);
    if (vret != 0)
      return vret;
  }
  
  return 0;
}

static int
verifying_clear(verify *self)
{
  lookup_clear((lookup *)self);
  Py_CLEAR(self->_verify_generations);
  Py_CLEAR(self->_verify_ro);
  return 0;
}


static void
verifying_dealloc(verify *self)
{
  verifying_clear(self);
  Py_TYPE(self)->tp_free((PyObject*)self);
}

/*  
    def changed(self, originally_changed):
        super(VerifyingBasePy, self).changed(originally_changed)
        self._verify_ro = self._registry.ro[1:]
        self._verify_generations = [r._generation for r in self._verify_ro]
*/
static PyObject *
_generations_tuple(PyObject *ro)
{
  int i, l;
  PyObject *generations;
  
  l = PyTuple_GET_SIZE(ro);
  generations = PyTuple_New(l);
  for (i=0; i < l; i++)
    {
      PyObject *generation;
      
      generation = PyObject_GetAttr(PyTuple_GET_ITEM(ro, i), str_generation);
      if (generation == NULL)
        {
          Py_DECREF(generations);
          return NULL;
        }
      PyTuple_SET_ITEM(generations, i, generation);
    }

  return generations;
}
static PyObject *
verifying_changed(verify *self, PyObject *ignored)
{
  PyObject *t, *ro;

  verifying_clear(self);

  t = PyObject_GetAttr(OBJECT(self), str_registry);
  if (t == NULL)
    return NULL;
  ro = PyObject_GetAttr(t, strro);
  Py_DECREF(t);
  if (ro == NULL)
    return NULL;

  t = PyObject_CallFunctionObjArgs(OBJECT(&PyTuple_Type), ro, NULL);
  Py_DECREF(ro);
  if (t == NULL)
    return NULL;

  ro = PyTuple_GetSlice(t, 1, PyTuple_GET_SIZE(t));
  Py_DECREF(t);
  if (ro == NULL)
    return NULL;
  
  self->_verify_generations = _generations_tuple(ro);
  if (self->_verify_generations == NULL)
    {
      Py_DECREF(ro);
      return NULL;
    }

  self->_verify_ro = ro;

  Py_INCREF(Py_None);
  return Py_None;
}

/*  
    def _verify(self):
        if ([r._generation for r in self._verify_ro]
            != self._verify_generations):
            self.changed(None)
*/
static int
_verify(verify *self)
{
  PyObject *changed_result;

  if (self->_verify_ro != NULL && self->_verify_generations != NULL)
    {
      PyObject *generations;
      int changed;

      generations = _generations_tuple(self->_verify_ro);
      if (generations == NULL)
        return -1;

      changed = PyObject_RichCompareBool(self->_verify_generations, 
					 generations, Py_NE);
      Py_DECREF(generations);
      if (changed == -1)
        return -1;
      
      if (changed == 0)
        return 0;
    }

  changed_result = PyObject_CallMethodObjArgs(OBJECT(self), strchanged, 
                                              Py_None, NULL);
  if (changed_result == NULL)
    return -1;

  Py_DECREF(changed_result);
  return 0;
}

static PyObject *
verifying_lookup(verify *self, PyObject *args, PyObject *kwds)
{
  static char *kwlist[] = {"required", "provided", "name", "default", NULL};
  PyObject *required, *provided, *name=NULL, *default_=NULL;

  if (! PyArg_ParseTupleAndKeywords(args, kwds, "OO|OO", kwlist,
                                    &required, &provided, &name, &default_))
    return NULL; 

  if (_verify(self) < 0)
    return NULL;

  return _lookup((lookup *)self, required, provided, name, default_);
}

static PyObject *
verifying_lookup1(verify *self, PyObject *args, PyObject *kwds)
{
  static char *kwlist[] = {"required", "provided", "name", "default", NULL};
  PyObject *required, *provided, *name=NULL, *default_=NULL;

  if (! PyArg_ParseTupleAndKeywords(args, kwds, "OO|OO", kwlist,
                                    &required, &provided, &name, &default_))
    return NULL; 

  if (_verify(self) < 0)
    return NULL;

  return _lookup1((lookup *)self, required, provided, name, default_);
}

static PyObject *
verifying_adapter_hook(verify *self, PyObject *args, PyObject *kwds)
{
  static char *kwlist[] = {"provided", "object", "name", "default", NULL};
  PyObject *object, *provided, *name=NULL, *default_=NULL;

  if (! PyArg_ParseTupleAndKeywords(args, kwds, "OO|OO", kwlist,
                                    &provided, &object, &name, &default_))
    return NULL; 

  if (_verify(self) < 0)
    return NULL;

  return _adapter_hook((lookup *)self, provided, object, name, default_);
}

static PyObject *
verifying_queryAdapter(verify *self, PyObject *args, PyObject *kwds)
{
  static char *kwlist[] = {"object", "provided", "name", "default", NULL};
  PyObject *object, *provided, *name=NULL, *default_=NULL;

  if (! PyArg_ParseTupleAndKeywords(args, kwds, "OO|OO", kwlist,
                                    &object, &provided, &name, &default_))
    return NULL; 

  if (_verify(self) < 0)
    return NULL;

  return _adapter_hook((lookup *)self, provided, object, name, default_);
}

static PyObject *
verifying_lookupAll(verify *self, PyObject *args, PyObject *kwds)
{
  static char *kwlist[] = {"required", "provided", NULL};
  PyObject *required, *provided;

  if (! PyArg_ParseTupleAndKeywords(args, kwds, "OO", kwlist,
                                    &required, &provided))
    return NULL; 

  if (_verify(self) < 0)
    return NULL;

  return _lookupAll((lookup *)self, required, provided);
}

static PyObject *
verifying_subscriptions(verify *self, PyObject *args, PyObject *kwds)
{
  static char *kwlist[] = {"required", "provided", NULL};
  PyObject *required, *provided;

  if (! PyArg_ParseTupleAndKeywords(args, kwds, "OO", kwlist,
                                    &required, &provided))
    return NULL; 

  if (_verify(self) < 0)
    return NULL;

  return _subscriptions((lookup *)self, required, provided);
}

static struct PyMethodDef verifying_methods[] = {
  {"changed",	   (PyCFunction)verifying_changed,	  METH_O,        ""},
  {"lookup",	   (PyCFunction)verifying_lookup,	  METH_KEYWORDS, ""},
  {"lookup1",	   (PyCFunction)verifying_lookup1,	  METH_KEYWORDS, ""},
  {"queryAdapter",  (PyCFunction)verifying_queryAdapter,  METH_KEYWORDS, ""},
  {"adapter_hook",  (PyCFunction)verifying_adapter_hook,  METH_KEYWORDS, ""},
  {"lookupAll",	   (PyCFunction)verifying_lookupAll,	  METH_KEYWORDS, ""},
  {"subscriptions", (PyCFunction)verifying_subscriptions, METH_KEYWORDS, ""},
  {NULL,	    NULL}		/* sentinel */
};

static PyTypeObject VerifyingBase = {
	PyVarObject_HEAD_INIT(NULL, 0)
	/* tp_name           */ "_zope_interface_coptimizations."
                                "VerifyingBase",
	/* tp_basicsize      */ sizeof(verify),
	/* tp_itemsize       */ 0,
	/* tp_dealloc        */ (destructor)&verifying_dealloc,
	/* tp_print          */ (printfunc)0,
	/* tp_getattr        */ (getattrfunc)0,
	/* tp_setattr        */ (setattrfunc)0,
	/* tp_compare        */ 0,
	/* tp_repr           */ (reprfunc)0,
	/* tp_as_number      */ 0,
	/* tp_as_sequence    */ 0,
	/* tp_as_mapping     */ 0,
	/* tp_hash           */ (hashfunc)0,
	/* tp_call           */ (ternaryfunc)0,
	/* tp_str            */ (reprfunc)0,
        /* tp_getattro       */ (getattrofunc)0,
        /* tp_setattro       */ (setattrofunc)0,
        /* tp_as_buffer      */ 0,
        /* tp_flags          */ Py_TPFLAGS_DEFAULT
				| Py_TPFLAGS_BASETYPE 
                          	| Py_TPFLAGS_HAVE_GC,
	/* tp_doc            */ "",
        /* tp_traverse       */ (traverseproc)verifying_traverse,
        /* tp_clear          */ (inquiry)verifying_clear,
        /* tp_richcompare    */ (richcmpfunc)0,
        /* tp_weaklistoffset */ (long)0,
        /* tp_iter           */ (getiterfunc)0,
        /* tp_iternext       */ (iternextfunc)0,
        /* tp_methods        */ verifying_methods,
        /* tp_members        */ 0,
        /* tp_getset         */ 0,
        /* tp_base           */ &LookupBase,
};

/* ========================== End: Lookup Bases ======================= */
/* ==================================================================== */



static struct PyMethodDef m_methods[] = {
  {"implementedBy", (PyCFunction)implementedBy, METH_O,
   "Interfaces implemented by a class or factory.\n"
   "Raises TypeError if argument is neither a class nor a callable."},
  {"getObjectSpecification", (PyCFunction)getObjectSpecification, METH_O,
   "Get an object's interfaces (internal api)"},
  {"providedBy", (PyCFunction)providedBy, METH_O,
   "Get an object's interfaces"},
  
  {NULL,	 (PyCFunction)NULL, 0, NULL}		/* sentinel */
};

#if  PY_MAJOR_VERSION >= 3
static char module_doc[] = "C optimizations for zope.interface\n\n";

static struct PyModuleDef _zic_module = {
	PyModuleDef_HEAD_INIT,
	"_zope_interface_coptimizations",
	module_doc,
	-1,
	m_methods,
	NULL,
	NULL,
	NULL,
	NULL
};
#endif

static PyObject *
init(void)
{
  PyObject *m;

#if  PY_MAJOR_VERSION < 3
#define DEFINE_STRING(S) \
  if(! (str ## S = PyString_FromString(# S))) return NULL
#else
#define DEFINE_STRING(S) \
  if(! (str ## S = PyUnicode_FromString(# S))) return NULL
#endif

  DEFINE_STRING(__dict__);
  DEFINE_STRING(__implemented__);
  DEFINE_STRING(__provides__);
  DEFINE_STRING(__class__);
  DEFINE_STRING(__providedBy__);
  DEFINE_STRING(extends);
  DEFINE_STRING(_implied);
  DEFINE_STRING(_implements);
  DEFINE_STRING(_cls);
  DEFINE_STRING(__conform__);
  DEFINE_STRING(_call_conform);
  DEFINE_STRING(_uncached_lookup);
  DEFINE_STRING(_uncached_lookupAll);
  DEFINE_STRING(_uncached_subscriptions);
  DEFINE_STRING(_registry);
  DEFINE_STRING(_generation);
  DEFINE_STRING(ro);
  DEFINE_STRING(changed);
#undef DEFINE_STRING
  adapter_hooks = PyList_New(0);
  if (adapter_hooks == NULL)
    return NULL;
        
  /* Initialize types: */
  SpecType.tp_new = PyBaseObject_Type.tp_new;
  if (PyType_Ready(&SpecType) < 0)
    return NULL;
  OSDType.tp_new = PyBaseObject_Type.tp_new;
  if (PyType_Ready(&OSDType) < 0)
    return NULL;
  CPBType.tp_new = PyBaseObject_Type.tp_new;
  if (PyType_Ready(&CPBType) < 0)
    return NULL;

  InterfaceBase.tp_new = PyBaseObject_Type.tp_new;
  if (PyType_Ready(&InterfaceBase) < 0)
    return NULL;

  LookupBase.tp_new = PyBaseObject_Type.tp_new;
  if (PyType_Ready(&LookupBase) < 0)
    return NULL;

  VerifyingBase.tp_new = PyBaseObject_Type.tp_new;
  if (PyType_Ready(&VerifyingBase) < 0)
    return NULL;

  #if PY_MAJOR_VERSION < 3
  /* Create the module and add the functions */
  m = Py_InitModule3("_zope_interface_coptimizations", m_methods,
                     "C optimizations for zope.interface\n\n");
  #else
  m = PyModule_Create(&_zic_module);
  #endif
  if (m == NULL)
    return NULL;

  /* Add types: */
  if (PyModule_AddObject(m, "SpecificationBase", OBJECT(&SpecType)) < 0)
    return NULL;
  if (PyModule_AddObject(m, "ObjectSpecificationDescriptor", 
                         (PyObject *)&OSDType) < 0)
    return NULL;
  if (PyModule_AddObject(m, "ClassProvidesBase", OBJECT(&CPBType)) < 0)
    return NULL;
  if (PyModule_AddObject(m, "InterfaceBase", OBJECT(&InterfaceBase)) < 0)
    return NULL;
  if (PyModule_AddObject(m, "LookupBase", OBJECT(&LookupBase)) < 0)
    return NULL;
  if (PyModule_AddObject(m, "VerifyingBase", OBJECT(&VerifyingBase)) < 0)
    return NULL;
  if (PyModule_AddObject(m, "adapter_hooks", adapter_hooks) < 0)
    return NULL;
  return m;
}

PyMODINIT_FUNC
#if PY_MAJOR_VERSION < 3
init_zope_interface_coptimizations(void)
{
  init();
}
#else
PyInit__zope_interface_coptimizations(void)
{
  return init();
}
#endif
