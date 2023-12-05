from typing import Callable, TYPE_CHECKING, Iterable, Optional, Any, Dict

if TYPE_CHECKING:
    import sybil


#: The signature for an evaluator. See :ref:`developing-parsers`.
Evaluator = Callable[['sybil.Example'], Optional[str]]

#: The signature for a lexer. See :ref:`developing-parsers`.
#: Lexers must not set :attr:`~sybil.Region.parsed` or :attr:`~sybil.Region.evaluator`
#: on the :class:`~sybil.Region` instances they return.
Lexer = Callable[['sybil.Document'], Iterable['sybil.Region']]

#: The signature for a parser. See :ref:`developing-parsers`.
Parser = Callable[['sybil.Document'], Iterable['sybil.Region']]

# In the future, this could likely be a TypedDict when Python 3.8 is the minimum supported version
#: Mappings used to store lexemes for a :class:`~sybil.Region`.
LexemeMapping = Dict[str, Any]

