import threading

from PyQt5.QtWidgets import QInputDialog, QLineEdit, QVBoxLayout, QLabel

from electronfittexxcoin.i18n import _
from electronfittexxcoin.plugins import hook
from electronfittexxcoin.wallet import Standard_Wallet
from .ledger import LedgerPlugin
from ..hw_wallet.qt import QtHandlerBase, QtPluginBase
from electronfittexxcoin_gui.qt.util import *

#from btchip.btchipPersoWizard import StartBTChipPersoDialog

class Plugin(LedgerPlugin, QtPluginBase):
    icon_unpaired = ":icons/ledger_unpaired.png"
    icon_paired = ":icons/ledger.png"

    def create_handler(self, window):
        return Ledger_Handler(window)

    @hook
    def receive_menu(self, menu, addrs, wallet):
        if type(wallet) is not Standard_Wallet:
            return
        keystore = wallet.get_keystore()
        if type(keystore) == self.keystore_class and len(addrs) == 1:
            def show_address():
                keystore.thread.add(partial(self.show_address, wallet, addrs[0]))
            menu.addAction(_("Show on Ledger"), show_address)

class Ledger_Handler(QtHandlerBase):
    setup_signal = pyqtSignal()
    auth_signal = pyqtSignal(object)

    def __init__(self, win):
        super(Ledger_Handler, self).__init__(win, 'Ledger')
        self.setup_signal.connect(self.setup_dialog)
        self.auth_signal.connect(self.auth_dialog)

    def word_dialog(self, msg):
        response = QInputDialog.getText(self.top_level_window(), "Ledger Wallet Authentication", msg, QLineEdit.Password)
        if not response[1]:
            self.word = None
        else:
            self.word = str(response[0])
        self.done.set()
    
    def message_dialog(self, msg):
        self.clear_dialog()
        self.dialog = dialog = WindowModalDialog(self.top_level_window(), _("Ledger Status"))
        l = QLabel(msg)
        vbox = QVBoxLayout(dialog)
        vbox.addWidget(l)
        dialog.show()

    def auth_dialog(self, data):
        try:
            from .auth2fa import LedgerAuthDialog
        except ImportError as e:
            self.message_dialog(str(e))
            return
        dialog = LedgerAuthDialog(self, data)
        dialog.exec_()
        self.word = dialog.pin
        self.done.set()
                    
    def get_auth(self, data):
        self.done.clear()
        self.auth_signal.emit(data)
        self.done.wait()
        return self.word
        
    def get_setup(self):
        self.done.clear()
        self.setup_signal.emit()
        self.done.wait()
        return 
        
    def setup_dialog(self):
        dialog = StartBTChipPersoDialog()
        dialog.exec_()


        
        
        
        
