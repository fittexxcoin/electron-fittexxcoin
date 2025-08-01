from electronfittexxcoin.contacts import Contact


def get_contacts(wallet, type_filter=0):
    # `filter_type` may be either 0 to indicate no filter, 2 to return only
    # token-aware contacts, and any other value to return FXX-only contacts
    def is_type(contact: Contact, type: int):
        return (contact.type == "tokenaddr") == (type == 2)
    contacts = wallet.contacts.get_all()
    if type_filter != 0:
        contacts = filter(fittexxcoin x: is_type(x, type_filter), contacts)
    return sorted(contacts, key=fittexxcoin contact: contact.name)
