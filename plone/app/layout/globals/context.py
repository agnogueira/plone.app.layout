from zope.interface import implements
from zope.component import getMultiAdapter, queryMultiAdapter
from plone.memoize.view import memoize

from Acquisition import aq_base, aq_inner, aq_parent
from Products.Five.browser import BrowserView

from Products.CMFPlone.interfaces import IBrowserDefault
from Products.CMFPlone.interfaces import INonStructuralFolder
from Products.CMFPlone.interfaces.NonStructuralFolder import INonStructuralFolder \
     as z2INonStructuralFolder

from Products.CMFPlone import utils

from interfaces import IContextState

class ContextState(BrowserView):
    """Information about the state of the current context
    """
    
    implements(IContextState)
    
    @memoize
    def current_page_url(self):
        url = self.current_base_url()
        query = self.request.get('QUERY_STRING', None)
        if query:
            url += '?' + query
        return url
        
    @memoize
    def current_base_url(self):
        return self.request.get('ACTUAL_URL',
                 self.request.get('VIRTUAL_URL',
                   self.request.get('URL', 
                     self.context.absolute_url())))
                             
    @memoize
    def canonical_object(self):
        if self.is_default_page():
            return self.parent()
        else:
            return self.context
            
    @memoize
    def canonical_object_url(self):
        return self.canonical_object().absolute_url()
            
    @memoize
    def view_template_id(self):
        context = aq_inner(self.context)
        browserDefault = IBrowserDefault(context, None)
        
        if browserDefault is not None:
            try:
                return browserDefault.getLayout()
            except AttributeError:
                # Might happen if FTI didn't migrate yet.
                pass

        action = self._lookupTypeActionTemplate('object/view')
        if not action:
            action = self._lookupTypeActionTemplate('folder/folderlisting')

        return action

    @memoize
    def is_view_template(self):
        current_url = self.current_base_url()
        object_url = self.object_url()
        
        if current_url == object_url:
            return True
        elif current_url == object_url + '/view':
            return True
        
        template_id = self.view_template_id()
        if current_url == "%s/%s" % (object_url, template_id):
            return True
        elif current_url == "%s/@@%s" % (object_url, template_id):
            return True
        
        return False

    @memoize
    def object_url(self):
        return aq_inner(self.context).absolute_url()
        
    @memoize
    def object_title(self):
        context = aq_inner(self.context)
        return utils.pretty_title_or_id(context, context)
        
    @memoize
    def workflow_state(self):
        tools = getMultiAdapter((self.context, self.request), name='plone_tools')
        return tools.workflow().getInfoFor(aq_inner(self.context), 'review_state', None)
    
    @memoize
    def parent(self):
        return aq_parent(aq_inner(self.context))

    @memoize
    def folder(self):
        if self.is_structural_folder() and not self.is_default_page():
            return aq_inner(self.context)
        else:
            return self.parent()
    
    @memoize
    def is_folderish(self):
        return bool(getattr(aq_base(aq_inner(self.context)), 'isPrincipiaFolderish', False))
            
    @memoize
    def is_structural_folder(self):
        folderish = self.is_folderish()
        context = aq_inner(self.context)
        if not folderish:
            return False
        elif INonStructuralFolder.providedBy(context):
            return False
        elif z2INonStructuralFolder.isImplementedBy(context):
            # BBB: for z2 interface compat
            return False
        else:
            return folderish
        
    @memoize
    def is_default_page(self):
        context = aq_inner(self.context)
        container = aq_parent(context)
        if not container:
            return False
        view = getMultiAdapter((container, self.request), name='default_page')
        return view.isDefaultPage(context)
    
    @memoize
    def is_portal_root(self):
        context = aq_inner(self.context)
        portal_state = getMultiAdapter((context, self.request), name=u'plone_portal_state')
        portal = portal_state.portal()
        return aq_base(context) is aq_base(portal) or \
                (self.is_default_page() and aq_base(self.parent()) is aq_base(portal))
    
    @memoize
    def is_editable(self):
        tools = getMultiAdapter((self.context, self.request), name='plone_tools')
        return bool(tools.membership().checkPermission('Modify portal content', aq_inner(self.context)))
    
    @memoize
    def is_locked(self):
        # plone_lock_info is registered on marker interface ITTWLockable, since
        # not everything may want to parttake in its lock-stealing ways.
        lock_info = queryMultiAdapter((self.context, self.request), name='plone_lock_info')
        if lock_info is not None:
            return lock_info.is_locked_for_current_user()
        else:
            context = aq_inner(self.context)
            lockable = getattr(context.aq_explicit, 'wl_isLocked', None) is not None
            return lockable and context.wl_isLocked()
                            
    @memoize
    def actions(self):
        tools = getMultiAdapter((self.context, self.request), name='plone_tools')
        return tools.actions().listFilteredActionsFor(aq_inner(self.context))
        
    @memoize
    def keyed_actions(self):
        actions = self.actions()
        keyed_actions = {}
        for category in actions.keys():
            keyed_actions[category] = {}
            for action in actions[category]:
                id = action.get('id', None)
                if id is not None:
                    keyed_actions[category][id] = action.copy()
        return keyed_actions
        
    # Helper methods
    def _lookupTypeActionTemplate(self, actionId):
        context = aq_inner(self.context)
        fti = context.getTypeInfo()
        try:
            # XXX: This isn't quite right since it assumes the action starts with ${object_url}
            action = fti.getActionInfo(actionId)['url'].split('/')[-1]
        except ValueError:
            # If the action doesn't exist, stop
            return None

        # Try resolving method aliases because we need a real template_id here
        action = fti.queryMethodID(action, default = action, context = context)

        # Strip off leading /
        if action and action[0] == '/':
            action = action[1:]
        return action