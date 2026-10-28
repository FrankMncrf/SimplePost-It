# SimplePost-It — instalación en Linux, común a install.sh y a los paquetes.
#   make install DESTDIR=/tmp/pkg PREFIX=/usr
PREFIX ?= /usr/local
LIBDIR ?= $(PREFIX)/lib/simplepostit
BINDIR ?= $(PREFIX)/bin
DATADIR ?= $(PREFIX)/share
DOCDIR ?= $(DATADIR)/doc/simplepostit
LICENSEDIR ?= $(DATADIR)/licenses/simplepostit

.PHONY: all install uninstall test

all:

test:
	QT_QPA_PLATFORM=offscreen python3 -m unittest discover -v -s tests

install:
	install -Dm755 simplepostit.py $(DESTDIR)$(LIBDIR)/simplepostit.py
	install -Dm644 i18n/en.json $(DESTDIR)$(LIBDIR)/i18n/en.json
	install -Dm644 CHANGELOG.md $(DESTDIR)$(LIBDIR)/CHANGELOG.md
	install -d $(DESTDIR)$(BINDIR)
	ln -sf $(LIBDIR)/simplepostit.py $(DESTDIR)$(BINDIR)/simplepostit
	install -Dm644 data/simplepostit.desktop $(DESTDIR)$(DATADIR)/applications/simplepostit.desktop
	install -Dm644 data/simplepostit.svg $(DESTDIR)$(DATADIR)/icons/hicolor/scalable/apps/simplepostit.svg
	install -Dm644 README.md $(DESTDIR)$(DOCDIR)/README.md
	install -Dm644 LICENSE $(DESTDIR)$(LICENSEDIR)/LICENSE

uninstall:
	rm -rf $(DESTDIR)$(LIBDIR) $(DESTDIR)$(DOCDIR) $(DESTDIR)$(LICENSEDIR)
	rm -f $(DESTDIR)$(BINDIR)/simplepostit \
		$(DESTDIR)$(DATADIR)/applications/simplepostit.desktop \
		$(DESTDIR)$(DATADIR)/icons/hicolor/scalable/apps/simplepostit.svg
