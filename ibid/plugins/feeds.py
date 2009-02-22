import re
from datetime import datetime
import logging

from sqlalchemy import Column, Integer, Unicode, DateTime, UnicodeText, ForeignKey, Table
from sqlalchemy.sql import func
import feedparser
from html2text import html2text_file

import ibid
from ibid.plugins import Processor, match, authorise
from ibid.models import Base

help = {'feeds': u'Displays articles from RSS and Atom feeds'}

log = logging.getLogger('plugins.feeds')

class Feed(Base):
    __table__ = Table('feeds', Base.metadata,
    Column('id', Integer, primary_key=True),
    Column('name', Unicode(32), unique=True, nullable=False),
    Column('url', UnicodeText, nullable=False),
    Column('identity_id', Integer, ForeignKey('identities.id'), nullable=False),
    Column('time', DateTime, nullable=False),
    useexisting=True)
    
    feed = None
    entries = None

    def __init__(self, name, url, identity_id):
        self.name = name
        self.url = url
        self.identity_id = identity_id
        self.time = datetime.now()

    def is_valid(self):
        self.update()
        if self.feed['version']:
            return True
        return False

    def update(self):
        self.feed = feedparser.parse(self.url)
        self.entries = self.feed['entries']

class Manage(Processor):
    """add feed <url> as <name>
    list feeds
    remove <name> feed"""
    feature = 'feeds'

    permission = u'feeds'

    @match(r'^add\s+feed\s+(.+?)\s+as\s+(.+?)$')
    @authorise
    def add(self, event, url, name):
        session = ibid.databases.ibid()
        feed = session.query(Feed).filter(func.lower(Feed.name)==name.lower()).first()

        if feed:
            event.addresponse(u"I already have the %s feed" % name)
        else:
            feed = Feed(unicode(name), unicode(url), event.identity)

        if feed.is_valid():
            session.save(feed)
            session.flush()
            event.addresponse(True)
            log.info(u"Added feed '%s' by %s/%s (%s): %s (Found %s entries)", name, event.account, event.identity, event.sender, url, len(feed.entries))
        else:
            event.addresponse(u"Sorry, I could not add the %s feed. %s is not a valid feed" % (name,url))

        session.close()

    @match(r'^list\s+feeds$')
    def list(self, event):
        session = ibid.databases.ibid()
        feeds = session.query(Feed).all()
        if feeds:
            event.addresponse(u', '.join([feed.name for feed in feeds]))
        else:
            event.addresponse(u"I don't know about any feeds")

    @match(r'^remove\s+(.+?)\s+feed$')
    @authorise
    def remove(self, event, name):
        session = ibid.databases.ibid()
        feed = session.query(Feed).filter(func.lower(Feed.name)==name.lower()).first()

        if not feed:
            event.addresponse(u"I don't have the %s feed anyway" % name)
        else:
            session.delete(feed)
            log.info(u"Deleted feed '%s' by %s/%s (%s): %s", name, event.account, event.identity, event.sender, feed.url)
            session.flush()
            event.addresponse(True)

        session.close()

class Retrieve(Processor):
    """(latest|last) [ <count> ] articles from <name> [ starting [(at|from)] <number> ]
    article ( <number> | /<pattern>/ ) from <name>"""
    feature = 'feeds'

    @match(r'^(?:latest|last)\s+(?:(\d+)\s+)?articles\s+from\s+(.+?)(?:\s+start(?:ing)?\s+(?:at\s+|from\s+)?(\d+))?$')
    def list(self, event, number, name, start):
        number = number and int(number) or 10
        start = start and int(start) or 0

        session = ibid.databases.ibid()
        feed = session.query(Feed).filter(func.lower(Feed.name)==name.lower()).first()
        session.close()

        if not feed:
            event.addresponse(u"I don't know about the %s feed" % name)
            return

        feed.update()
        if not feed.entries:
            event.addresponse(u"I can't access that feed")
            return

        event.addresponse(u', '.join(['%s: "%s"' % (feed.entries.index(entry), html2text_file(entry.title, None).strip()) for entry in feed.entries[start:number+start]]))

    @match(r'^article\s+(?:(\d+)|/(.+?)/)\s+from\s+(.+?)$')
    def article(self, event, number, pattern, name):
        session = ibid.databases.ibid()
        feed = session.query(Feed).filter(func.lower(Feed.name)==name.lower()).first()
        session.close()

        if not feed:
            event.addresponse(u"I don't know about the %s feed" % name)
            return

        feed.update() 
        if not feed.entries:
            event.addresponse(u"I can't access that feed")
            return
        article = None

        if number:
            if int(number) >= len(feed.entries):
                event.addresponse(u"That's old news dude")
                return
            article = feed.entries[int(number)]

        else:
            pattern = re.compile(pattern, re.I)
            for entry in feed.entries:
                if pattern.search(entry.title):
                    article = entry
                    break

            if not article:
                event.addresponse(u"Are you making up news again?")
                return

        if 'summary' in article:
            summary = html2text_file(article.summary, None)
        else:
            if article.content[0].type in ('application/xhtml+xml', 'text/html'):
                summary = html2text_file(article.content[0].value, None)
            else:
                summary = article.content[0].value

        event.addresponse(u'"%s" %s : %s' % (html2text_file(article.title, None).strip(), article.link, summary))

# vi: set et sta sw=4 ts=4:
