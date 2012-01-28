#     Copyright 2012, Kay Hayen, mailto:kayhayen@gmx.de
#
#     Part of "Nuitka", an optimizing Python compiler that is compatible and
#     integrates with CPython, but also works on its own.
#
#     If you submit patches or make the software available to licensors of
#     this software in either form, you automatically them grant them a
#     license for your part of the code under "Apache License 2.0" unless you
#     choose to remove this notice.
#
#     Kay Hayen uses the right to license his code under only GPL version 3,
#     to discourage a fork of Nuitka before it is "finished". He will later
#     make a new "Nuitka" release fully under "Apache License 2.0".
#
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, version 3 of the License.
#
#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#     Please leave the whole of this copyright notice intact.
#
""" Node base classes.

These classes provide the generic base classes available for nodes.

"""


from nuitka.odict import OrderedDict

from nuitka import (
    Variables,
    Tracing,
    TreeXML
)

from . import UsageCheck

lxml = TreeXML.lxml

class NodeCheckMetaClass( type ):
    kinds = set()

    def __new__( mcs, name, bases, dictionary ):
        # Merge the tags with the base classes in a non-overriding
        # way, instead add them up.
        if "tags" not in dictionary:
            dictionary[ "tags" ] = ()

        for base in bases:
            if hasattr( base, "tags" ):
                dictionary[ "tags" ] += getattr( base, "tags" )

        # Uncomment this for debug view of class tags.
        # print name, dictionary[ "tags" ]

        return type.__new__( mcs, name, bases, dictionary )

    def __init__( mcs, name, bases, dictionary ):
        if not name.endswith( "Base" ):
            assert ( "kind" in dictionary ), name
            kind = dictionary[ "kind" ]

            assert type( kind ) is str, name
            assert kind not in NodeCheckMetaClass.kinds, name

            NodeCheckMetaClass.kinds.add( kind )

            def convert( value ):
                if value in ( "AND", "OR", "NOT" ):
                    return value
                else:
                    return value.title()

            kind_to_name_part = "".join(
                [ convert( x ) for x in kind.split( "_" ) ]
            )
            assert name.endswith( kind_to_name_part ), ( name, kind_to_name_part )

            # Automatically add checker methods for everything to the common base class
            checker_method = "is" + kind_to_name_part

            if name.startswith( "CPython" ):
                checker_method = checker_method.replace( "CPython", "" )

            def checkKind( self ):
                return self.kind == kind

            if not hasattr( CPythonNodeBase, checker_method ):
                setattr( CPythonNodeBase, checker_method, checkKind )

            # Tags mechanism, so node classes can be tagged with inheritance or freely,
            # the "tags" attribute is not overloaded, but added. Absolutely not obvious
            # and a trap set for the compiler by itself.

        type.__init__( mcs, name, bases, dictionary )

# For every node type, there is a test, and then some more members, pylint: disable=R0904

# For Python2/3 compatible source, we create a base class that has the metaclass used and
# doesn't require making a choice.
CPythonNodeMetaClassBase = NodeCheckMetaClass( "CPythonNodeMetaClassBase", (object, ), {} )

class CPythonNodeBase( CPythonNodeMetaClassBase ):
    kind = None

    tags = ()

    # Must be overloaded by expressions.
    value_friend_maker = None

    def __init__( self, source_ref ):
        assert source_ref is not None
        assert source_ref.line is not None

        self.parent = None

        self.source_ref = source_ref

    def __repr__( self ):
        # This is to avoid crashes, because of bugs in detail. pylint: disable=W0702
        try:
            detail = self.getDetail()
        except:
            detail = "detail raises exception"

        if detail == "":
            return "<Node %s>" % self.getDescription()
        else:
            return "<Node %s %s>" % ( self.getDescription(), detail )

    def getDescription( self ):
        """ Description of the node, intented for use in __repr__ and graphical display.

        """
        return "%s at %s" % ( self.kind, self.source_ref.getAsString() )

    def getDetails( self ):
        """ Details of the node, intented for use in __repr__ and dumps.

        """
        # Virtual method, pylint: disable=R0201,W0613
        return {}

    def getDetail( self ):
        """ Details of the node, intented for use in __repr__ and graphical display.

        """
        # Virtual method, pylint: disable=R0201,W0613
        return ""

    def getParent( self ):
        """ Parent of the node. Every node except modules have to have a parent.

        """

        if self.parent is None and not self.isModule():
            assert False, ( self,  self.source_ref )

        return self.parent

    def getParentExecInline( self ):
        """ Return the parent that is an inlined exec.

        """

        parent = self.getParent()

        while parent is not None and not parent.isStatementExecInline():
            parent = parent.getParent()

        return parent

    def getParentFunction( self ):
        """ Return the parent that is a function.

        """

        parent = self.getParent()

        while parent is not None and not parent.isExpressionFunctionBody():
            parent = parent.getParent()

        return parent

    def getParentClass( self ):
        """ Return the parent that is a class body.

        """

        parent = self.getParent()

        while parent is not None and not parent.isExpressionClassBody():
            parent = parent.getParent()

        return parent

    def getParentModule( self ):
        """ Return the parent that is module.

        """
        parent = self

        while not parent.isModule():
            if hasattr( parent, "provider" ):
                # After we checked, we can use it, will be much faster, pylint: disable=E1101
                parent = parent.provider
            else:
                parent = parent.getParent()

        return parent

    def isParentVariableProvider( self ):
        # Check if it's a closure giver or a class, in which cases it can provide
        # variables, pylint: disable=E1101
        return isinstance( self, CPythonClosureGiverNodeBase ) or self.isExpressionClassBody()

    def isClosureVariableTaker( self ):
        return self.hasTag( "closure_taker" )

    def getParentVariableProvider( self ):
        parent = self.getParent()

        while not parent.isParentVariableProvider():
            parent = parent.getParent()

        return parent

    def getSourceReference( self ):
        return self.source_ref

    def asXml( self ):
        result = lxml.etree.Element(
            "node",
            kind = self.__class__.__name__.replace( "CPython", "" ),
            line = "%s" % self.getSourceReference().getLineNumber()
        )

        for key, value in self.getDetails().iteritems():
            value = str( value )

            if value.startswith( "<" ) and value.endswith( ">" ):
                value = value[1:-1]

            result.set( key, str( value ) )

        for name, children in self.getVisitableNodesNamed():
            if type( children ) not in ( list, tuple ):
                children = ( children, )

            role = lxml.etree.Element(
                "role",
                name = name
            )

            result.append( role )

            for child in children:
                if child is not None:
                    role.append(
                        child.asXml()
                    )

        return result

    def dump( self, level = 0 ):
        Tracing.printIndented( level, self )
        Tracing.printSeparator( level )

        for visitable in self.getVisitableNodes():
            visitable.dump( level + 1 )

        Tracing.printSeparator( level )

    def isModule( self ):
        return self.kind in ( "MODULE", "PACKAGE" )

    def isExpression( self ):
        return self.kind.startswith( "EXPRESSION_" )

    def isStatement( self ):
        return self.kind.startswith( "STATEMENT_" )

    def isExpressionBuiltin( self ):
        return self.kind.startswith( "EXPRESSION_BUILTIN_" )

    def isOperation( self ):
        return self.kind.startswith( "EXPRESSION_OPERATION_" )

    def isExpressionOperationBool2( self ):
        return self.kind.startswith( "EXPRESSION_BOOL_" )

    def isAssignTargetSomething( self ):
        return self.kind.startswith( "ASSIGN_" )

    def isExpressionMakeSequence( self ):
        # Virtual method, pylint: disable=R0201,W0613
        return False

    def isNumberConstant( self ):
        # Virtual method, pylint: disable=R0201,W0613
        return False

    def visit( self, context, visitor ):
        visitor( self )

        for visitable in self.getVisitableNodes():
            visitable.visit( context, visitor )

    def getVisitableNodes( self ):
        # Virtual method, pylint: disable=R0201,W0613
        return ()

    def getVisitableNodesNamed( self ):
        assert self.getVisitableNodes.im_class == self.getVisitableNodesNamed.im_class, self.getVisitableNodes.im_class

        return ()

    def getChildNodesNotTagged( self, tag ):
        """ Get child nodes that do not have a given tag.

        """

        return [
            node
            for node in
            self.getVisitableNodes()
            if not node.hasTag( tag )
        ]


    def replaceWith( self, new_node ):
        self.parent.replaceChild( old_node = self, new_node = new_node )

    def getName( self ):
        # Virtual method, pylint: disable=R0201,W0613
        return None

    def mayHaveSideEffects( self ):
        """ Unless we are told otherwise, everything may have a side effect. """
        # Virtual method, pylint: disable=R0201,W0613

        return True

    def mayRaiseException( self, exception_type ):
        """ Unless we are told otherwise, everything may raise everything. """
        # Virtual method, pylint: disable=R0201,W0613

        return True

    def isIndexable( self ):
        """ Unless we are told otherwise, it's not indexable. """
        # Virtual method, pylint: disable=R0201,W0613

        return False

    def hasTag( self, tag ):
        return tag in self.__class__.tags

class CPythonCodeNodeBase( CPythonNodeBase ):
    def __init__( self, name, code_prefix, source_ref ):
        assert name is not None
        assert " " not in name
        assert "<" not in name

        CPythonNodeBase.__init__( self, source_ref = source_ref )

        self.name = name
        self.code_prefix = code_prefix

        # The code name is determined on demand only.
        self.code_name = None

        # The "UID" values of children kinds are kept here.
        self.uids = {}

    def getName( self ):
        return self.name

    def getFullName( self ):
        result = self.getName()

        current = self

        while True:
            current = current.getParent()

            if current is None:
                break

            name = current.getName()

            if name is not None:
                result = "%s__%s" % ( name, result )

        assert "<" not in result, result

        return result

    def getCodeName( self ):
        if self.code_name is None:
            search = self.parent

            while search is not None:
                if isinstance( search, CPythonCodeNodeBase ):
                    break

                search = search.parent

            parent_name = search.getCodeName()

            uid = "_%d" % search.getChildUID( self )

            if isinstance( self, CPythonCodeNodeBase ):
                name = uid + "_" + self.name
            else:
                name = uid

            self.code_name = "%s%s_of_%s" % ( self.code_prefix, name, parent_name )

        return self.code_name

    def getChildUID( self, node ):
        if node.kind not in self.uids:
            self.uids[ node.kind ] = 0

        self.uids[ node.kind ] += 1

        return self.uids[ node.kind ]

class CPythonChildrenHaving:
    named_children = ()

    def __init__( self, values ):
        assert len( self.named_children )
        assert type( self.named_children ) is tuple

        for key in values.keys():
            assert key in self.named_children

        self.child_values = dict.fromkeys( self.named_children )
        self.child_values.update( values )

        for key, value in values.items():
            assert type( value ) is not list, key

            if type( value ) is tuple:
                assert None not in value, key

                for val in value:
                    val.parent = self
            elif value is not None:
                value.parent = self

    def setChild( self, name, value ):
        assert name in self.child_values, name

        if type( value ) is list:
            value = tuple( value )

        if type( value ) is tuple:
            for val in value:
                val.parent = self
        elif value is not None:
            value.parent = self

        self.child_values[ name ] = value

    def getChild( self, name ):
        assert name in self.child_values, name

        return self.child_values[ name ]

    @staticmethod
    def childGetter( name ):
        def getter( self ):
            return self.getChild( name )

        return getter

    @staticmethod
    def childSetter( name ):
        def setter( self, value ):
            self.setChild( name, value )

        return setter

    def getVisitableNodes( self ):
        result = []

        for name in self.named_children:
            value = self.child_values[ name ]

            if value is None:
                pass
            elif type( value ) is tuple:
                result += list( value )
            elif isinstance( value, CPythonNodeBase ):
                result.append( value )
            else:
                assert False, ( name, value, value.__class__ )

        return tuple( result )

    def getVisitableNodesNamed( self ):
        result = []

        for name in self.named_children:
            value = self.child_values[ name ]

            result.append( ( name, value ) )

        return result

    def replaceChild( self, old_node, new_node ):
        for key, value in self.child_values.items():
            if value is None:
                pass
            elif type( value ) is tuple:
                if old_node in value:
                    new_value = []

                    for val in value:
                        if val is not old_node:
                            new_value.append( val )
                        else:
                            new_value.append( new_node )

                    self.setChild( key, tuple( new_value ) )

                    break
            elif isinstance( value, CPythonNodeBase ):
                if old_node is value:
                    self.setChild( key, new_node )

                    break
            else:
                assert False, ( key, value, value.__class__ )
        else:
            raise AssertionError(
                "Didn't find child",
                old_node,
                "in",
                self
            )

        if new_node is not None:
            new_node.parent = old_node.parent


class CPythonClosureGiverNodeBase( CPythonCodeNodeBase ):
    """ Mixin for nodes that provide variables for closure takers. """
    def __init__( self, name, code_prefix, source_ref ):
        CPythonCodeNodeBase.__init__(
            self,
            name        = name,
            code_prefix = code_prefix,
            source_ref  = source_ref
        )

        self.providing = OrderedDict()

    def hasProvidedVariable( self, variable_name ):
        return variable_name in self.providing

    def getProvidedVariable( self, variable_name ):
        if variable_name not in self.providing:
            self.providing[ variable_name ] = self.createProvidedVariable(
                variable_name = variable_name
            )

        return self.providing[ variable_name ]

    def createProvidedVariable( self, variable_name ):
        # Virtual method, pylint: disable=R0201,W0613
        assert type( variable_name ) is str

        return None

    def registerProvidedVariables( self, variables ):
        for variable in variables:
            self.registerProvidedVariable( variable )

    def registerProvidedVariable( self, variable ):
        assert variable is not None

        self.providing[ variable.getName() ] = variable

    def getProvidedVariables( self ):
        return self.providing.values()

    def reconsiderVariable( self, variable ):
        # TODO: Why doesn't this fit in as well.
        if self.isModule():
            return

        assert variable.getOwner() is self

        if variable.getName() in self.providing:
            assert self.providing[ variable.getName() ] is variable, (
                self.providing[ variable.getName() ], "is not", variable, self
            )

            if not variable.isShared():
                # TODO: The functions/classes should have have a clearer scope too.
                usages = UsageCheck.getVariableUsages( self, variable )

                if not usages:
                    del self.providing[ variable.getName() ]

class CPythonParameterHavingNodeBase( CPythonClosureGiverNodeBase ):
    def __init__( self, name, code_prefix, parameters, source_ref ):
        CPythonClosureGiverNodeBase.__init__(
            self,
            name        = name,
            code_prefix = code_prefix,
            source_ref  = source_ref
        )

        self.parameters = parameters
        self.parameters.setOwner( self )

        self.registerProvidedVariables(
            variables = self.parameters.getVariables()
        )

    def getParameters( self ):
        return self.parameters


class CPythonClosureTaker:
    """ Mixin for nodes that accept variables from closure givers. """

    tags = ( "closure_taker", "execution_border" )

    def __init__( self, provider ):
        assert self.__class__.early_closure is not None, self

        assert provider.isParentVariableProvider(), provider

        self.provider = provider

        self.taken = set()

        self.temp_variables = set()


    def getParentVariableProvider( self ):
        return self.provider

    def getClosureVariable( self, variable_name ):
        result = self.provider.getVariableForClosure(
            variable_name = variable_name
        )
        assert result is not None, variable_name

        # There is no maybe with closures. It means, it is closure variable in
        # this case.
        if result.isMaybeLocalVariable():
            # This mixin is used with nodes only, but doesn't want to inherit from
            # it, pylint: disable=E1101
            result = self.getParentModule().getVariableForClosure(
                variable_name = variable_name
            )

        return self.addClosureVariable( result )

    def addClosureVariable( self, variable, global_statement = False ):
        variable = variable.makeReference( self )

        if variable.isModuleVariable() and global_statement:
            variable.markFromGlobalStatement()

        self.taken.add( variable )

        return variable

    def getClosureVariables( self ):
        return tuple(
            sorted(
                [ take for take in self.taken if take.isClosureReference() ],
                key = lambda x : x.getName()
            )
        )

    def hasTakenVariable( self, variable_name ):
        for variable in self.taken:
            if variable.getName() == variable_name:
                return True
        else:
            return False

    def getTakenVariable( self, variable_name ):
        for variable in self.taken:
            if variable.getName() == variable_name:
                return variable
        else:
            return None

    # Normally it's good to lookup name references immediately, but in case of a function
    # body it is not allowed to do that, because a later assignment needs to be queried
    # first. Nodes need to indicate via this if they would like to resolve references at
    # the same time as assignments.
    early_closure = None

    def isEarlyClosure( self ):
        return self.early_closure

    def getTempVariable( self ):
        result = Variables.TempVariable(
            owner         = self,
            variable_name = "__tmp_%d" % len( self.temp_variables )
        )
        self.temp_variables.add( result )
        return result

    def getTempVariables( self ):
        return tuple( self.temp_variables )

    def setTempVariables( self, variables ):
        for variable in variables:
            assert variable.isTempVariable(), variable
            assert variable.getOwner() is self

        self.temp_variables = variables


class CPythonExpressionBuiltinSingleArgBase( CPythonChildrenHaving, CPythonNodeBase ):
    named_children = ( "value", )

    def __init__( self, value, source_ref ):
        CPythonNodeBase.__init__( self, source_ref = source_ref )

        CPythonChildrenHaving.__init__(
            self,
            values = {
                "value" : value,
            }
        )

    getValue = CPythonChildrenHaving.childGetter( "value" )