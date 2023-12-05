# -*- test-case-name: twisted.test.test_roots -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Twisted Python Roots: an abstract hierarchy representation for Twisted.

Maintainer: Glyph Lefkowitz
"""


from twisted.python import reflect


class NotSupportedError(NotImplementedError):
    """
    An exception meaning that the tree-manipulation operation
    you're attempting to perform is not supported.
    """


class Request:
    """I am an abstract representation of a request for an entity.

    I also function as the response.  The request is responded to by calling
    self.write(data) until there is no data left and then calling
    self.finish().
    """

    # This attribute should be set to the string name of the protocol being
    # responded to (e.g. HTTP or FTP)
    wireProtocol = None

    def write(self, data):
        """Add some data to the response to this request."""
        raise NotImplementedError("%s.write" % reflect.qual(self.__class__))

    def finish(self):
        """The response to this request is finished; flush all data to the network stream."""
        raise NotImplementedError("%s.finish" % reflect.qual(self.__class__))


class Entity:
    """I am a terminal object in a hierarchy, with no children.

    I represent a null interface; certain non-instance objects (strings and
    integers, notably) are Entities.

    Methods on this class are suggested to be implemented, but are not
    required, and will be emulated on a per-protocol basis for types which do
    not handle them.
    """

    def render(self, request):
        """
        I produce a stream of bytes for the request, by calling request.write()
        and request.finish().
        """
        raise NotImplementedError("%s.render" % reflect.qual(self.__class__))


class Collection:
    """I represent a static collection of entities.

    I contain methods designed to represent collections that can be dynamically
    created.
    """

    def __init__(self, entities=None):
        """Initialize me."""
        if entities is not None:
            self.entities = entities
        else:
            self.entities = {}

    def getStaticEntity(self, name):
        """Get an entity that was added to me using putEntity.

        This method will return 'None' if it fails.
        """
        return self.entities.get(name)

    def getDynamicEntity(self, name, request):
        """Subclass this to generate an entity on demand.

        This method should return 'None' if it fails.
        """

    def getEntity(self, name, request):
        """Retrieve an entity from me.

        I will first attempt to retrieve an entity statically; static entities
        will obscure dynamic ones.  If that fails, I will retrieve the entity
        dynamically.

        If I cannot retrieve an entity, I will return 'None'.
        """
        ent = self.getStaticEntity(name)
        if ent is not None:
            return ent
        ent = self.getDynamicEntity(name, request)
        if ent is not None:
            return ent
        return None

    def putEntity(self, name, entity):
        """Store a static reference on 'name' for 'entity'.

        Raises a KeyError if the operation fails.
        """
        self.entities[name] = entity

    def delEntity(self, name):
        """Remove a static reference for 'name'.

        Raises a KeyError if the operation fails.
        """
        del self.entities[name]

    def storeEntity(self, name, request):
        """Store an entity for 'name', based on the content of 'request'."""
        raise NotSupportedError("%s.storeEntity" % reflect.qual(self.__class__))

    def removeEntity(self, name, request):
        """Remove an entity for 'name', based on the content of 'request'."""
        raise NotSupportedError("%s.removeEntity" % reflect.qual(self.__class__))

    def listStaticEntities(self):
        """Retrieve a list of all name, entity pairs that I store references to.

        See getStaticEntity.
        """
        return self.entities.items()

    def listDynamicEntities(self, request):
        """A list of all name, entity that I can generate on demand.

        See getDynamicEntity.
        """
        return []

    def listEntities(self, request):
        """Retrieve a list of all name, entity pairs I contain.

        See getEntity.
        """
        return self.listStaticEntities() + self.listDynamicEntities(request)

    def listStaticNames(self):
        """Retrieve a list of the names of entities that I store references to.

        See getStaticEntity.
        """
        return self.entities.keys()

    def listDynamicNames(self):
        """Retrieve a list of the names of entities that I store references to.

        See getDynamicEntity.
        """
        return []

    def listNames(self, request):
        """Retrieve a list of all names for entities that I contain.

        See getEntity.
        """
        return self.listStaticNames()


class ConstraintViolation(Exception):
    """An exception raised when a constraint is violated."""


class Constrained(Collection):
    """A collection that has constraints on its names and/or entities."""

    def nameConstraint(self, name):
        """A method that determines whether an entity may be added to me with a given name.

        If the constraint is satisfied, return 1; if the constraint is not
        satisfied, either return 0 or raise a descriptive ConstraintViolation.
        """
        return 1

    def entityConstraint(self, entity):
        """A method that determines whether an entity may be added to me.

        If the constraint is satisfied, return 1; if the constraint is not
        satisfied, either return 0 or raise a descriptive ConstraintViolation.
        """
        return 1

    def reallyPutEntity(self, name, entity):
        Collection.putEntity(self, name, entity)

    def putEntity(self, name, entity):
        """Store an entity if it meets both constraints.

        Otherwise raise a ConstraintViolation.
        """
        if self.nameConstraint(name):
            if self.entityConstraint(entity):
                self.reallyPutEntity(name, entity)
            else:
                raise ConstraintViolation("Entity constraint violated.")
        else:
            raise ConstraintViolation("Name constraint violated.")


class Locked(Constrained):
    """A collection that can be locked from adding entities."""

    locked = 0

    def lock(self):
        self.locked = 1

    def entityConstraint(self, entity):
        return not self.locked


class Homogenous(Constrained):
    """A homogenous collection of entities.

    I will only contain entities that are an instance of the class or type
    specified by my 'entityType' attribute.
    """

    entityType = object

    def entityConstraint(self, entity):
        if isinstance(entity, self.entityType):
            return 1
        else:
            raise ConstraintViolation(f"{entity} of incorrect type ({self.entityType})")

    def getNameType(self):
        return "Name"

    def getEntityType(self):
        return self.entityType.__name__
