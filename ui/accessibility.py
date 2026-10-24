"""Use Tk's real platform accessibility API when the runtime provides it.

Legacy Tk continues to run but does not get reported as a screen-reader backend.
No Python-only accessible_name attribute is presented as OS accessibility.
"""
import tkinter as tk


def available(widget):
    root = widget._root()
    if not hasattr(root, '_myl_a11y_native'):
        root._myl_a11y_native = bool(root.tk.call('info', 'commands', '::tk::accessible::set_acc_role'))
        root._myl_a11y_errors = []
    return root._myl_a11y_native


def expose(widget, *, role, name, description='', value=None, action=None, state='normal'):
    if not available(widget):
        return False
    signature = (role, str(name), str(description), str(value), action, state)
    if getattr(widget, '_myl_a11y_signature', None) == signature:
        return True
    try:
        values = {'role': role, 'name': name, 'description': description, 'state': state}
        if widget.tk.call('tk', 'windowingsystem') == 'win32':
            # Tk 9.1's MSAA get_accName returns the description slot (its own
            # Button bindings also use that slot for visible labels). Keep the
            # actual label there and put optional explanatory text in help.
            values['description'] = name
            values['help'] = description
        if value is not None:
            values['value'] = value
        if action:
            values['action'] = action
        for key, content in values.items():
            # The public ensemble is a no-op when no speech reader was active
            # at startup. The native commands also support UIA/AX clients that
            # connect later, without changing any operating-system setting.
            widget.tk.call('::tk::accessible::set_acc_' + key, str(widget), str(content))
        widget._myl_a11y_signature = signature
        return True
    except tk.TclError as exc:
        widget._root()._myl_a11y_errors.append(str(exc))
        return False


def notify(widget, selection=False):
    if available(widget):
        try:
            widget.tk.call('::tk::accessible::' + ('emit_selection_change' if selection else 'emit_focus_change'), str(widget))
        except tk.TclError:
            pass  # Destroy/focus events can refer to a just-removed widget.


def name_control(widget, name, description=''):
    widget._myl_a11y_name = str(name)
    widget._myl_a11y_description = str(description)
    annotate(widget)


def annotate(widget):
    if not isinstance(widget, tk.Misc):
        return
    if not available(widget):
        return
    if hasattr(widget, '_sync_accessibility'):
        widget._sync_accessibility()
        return
    roles = {'Button': 'Button', 'TButton': 'Button', 'Entry': 'Entry', 'TEntry': 'Entry',
             'TCombobox': 'Combobox', 'Label': 'Label', 'TLabel': 'Label', 'Text': 'Text',
             'Listbox': 'Listbox', 'Treeview': 'Table', 'TProgressbar': 'Progressbar',
             'Checkbutton': 'Checkbutton', 'TCheckbutton': 'Checkbutton', 'TScale': 'Scale',
             'Spinbox': 'Spinbox', 'TSpinbox': 'Spinbox', 'TNotebook': 'Notebook'}
    role = roles.get(widget.winfo_class())
    if role is None:
        return
    def option(key, default=''):
        try:
            return widget.cget(key)
        except tk.TclError:
            return default
    name = getattr(widget, '_myl_a11y_name', '') or option('text')
    # Fields are explicitly named where their meaning matters; never use a
    # placeholder or the user's value as a substitute for a field label.
    if not name and role in {'Entry', 'Combobox', 'Spinbox'}:
        previous = list(widget.master.winfo_children())
        index = previous.index(widget)
        if index and isinstance(previous[index - 1], (tk.Label,)):
            name = previous[index - 1].cget('text')
    action = option('command') if role in {'Button', 'Checkbutton'} else None
    value = None
    if role in {'Entry', 'Combobox', 'Spinbox'}:
        value = widget.get()
    elif role == 'Table':
        selected = widget.selection()
        value = ' | '.join(map(str, widget.item(selected[0], 'values'))) if selected else ''
    expose(widget, role=role, name=name or role,
           description=getattr(widget, '_myl_a11y_description', ''), value=value, action=action,
           state=str(option('state', 'normal')))


def install(root):
    if not available(root) or getattr(root, '_myl_a11y_installed', False):
        return
    root._myl_a11y_installed = True
    def mapped(event):
        widget = event.widget
        if not isinstance(widget, tk.Misc):
            return
        # Tk's own Map handler initializes default attributes. Apply the app's
        # semantic names/actions after that handler has completed.
        def finish_annotation():
            if widget.winfo_exists():
                widget._myl_a11y_signature = None
                annotate(widget)
        widget.after_idle(finish_annotation)
        if isinstance(widget, (tk.Tk, tk.Toplevel)):
            def register():
                if widget.winfo_exists():
                    widget.tk.call('::tk::accessible::add_acc_object', str(widget))
            widget.after_idle(register)
    def focused(event):
        if isinstance(event.widget, tk.Misc):
            event.widget._myl_a11y_signature = None
            annotate(event.widget)
            notify(event.widget)
    root.bind_all('<Map>', mapped, add='+')
    root.bind_all('<FocusIn>', focused, add='+')
    root.bind_all('<<TreeviewSelect>>', lambda event: (annotate(event.widget), notify(event.widget, True)), add='+')
    root.bind_all('<<ComboboxSelected>>', lambda event: (annotate(event.widget), notify(event.widget, True)), add='+')
    root.bind_all('<KeyRelease>', lambda event: annotate(event.widget), add='+')
