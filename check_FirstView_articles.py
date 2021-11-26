#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""

@author: Adrien Wehrlé, University of Zurich, Switzerland

"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
import smtplib
from email.mime.text import MIMEText
import imaplib
import email
from email.header import decode_header


class EmailAlert:
    """
    Check for new FirstView articles and send email alert through a
    specified sender account.
    """

    def __init__(self, sender_user: str, sender_authfile: str) -> None:
        """
        Initialize sender account

        :param sender_user: email address that will be used to send email alerts
        :param sender_authfile: path to text file containing user credentials

        :returns: None
        """

        self.sender_user = sender_user
        self.sender_authfile = sender_authfile

    def login_smtp(self, user: str, auth_file: str) -> smtplib.SMTP:
        """
        Login on an SMTP server that requires authentification.

        :param user: User email address
        :param auth_file: Path to authentification file

        :returns smtp_session: Open SMTP session
        """

        # extract password from authentication file
        password = str(np.genfromtxt(auth_file, dtype="str"))

        # create a SMTP instance
        smtp_session = smtplib.SMTP("smtp.live.com", 587)

        # identify using EHLO
        smtp_session.ehlo()
        # put connection in TLS mode
        smtp_session.starttls()
        # re-identify as an encrypted connection
        smtp_session.ehlo()

        # login on the SMTP server
        smtp_session.login(user, password)

        return smtp_session

    def login_imap(self, user: str, auth_file: str) -> imaplib.IMAP4_SSL:
        """
        Login on an IMAP4 server that requires authentification.

        :param user: User email address
        :param auth_file: Path to authentification file

        :returns smtp_session: Open IMAP4 session
        """

        # extract password from authentication file
        password = str(np.genfromtxt(auth_file, dtype="str"))

        # create an IMAP instance over an SSL encrypted socket
        imap_session = imaplib.IMAP4_SSL("smtp.live.com")

        # login on the IMAP4 server
        imap_session.login(user, password)

        return imap_session

    def journal_url_to_plaintext(self, journal_url: str) -> str:
        """
        Convert journal URL string to plain text.

        :param url: Journal url

        :returns ptxt_journal_name: Journal name in plain text
        """

        # extract journal name
        journal_name = [
            string for string in journal_url.split("/") if "-of-" in string
        ][0]

        # extract words in journal name
        journal_words = journal_name.split("-")

        # convert to plain text and capitalize words that are needed
        ptxt_journal_name = " ".join(
            [word.capitalize() if word != "of" else word for word in journal_words]
        )

        return ptxt_journal_name

    def check_emails(self, new_FirstView_url: str) -> bool:
        """
        Check if user already received an email alert for a given
        FirstView article.

        :param new_FirstView_url: URL of the new FirstView article

        :returns alert_sent: True if alert has already been sent
        """

        # extract journal name in plain text
        journal_name = self.journal_url_to_plaintext(new_FirstView_url)

        # build expected email object
        new_FirstView_subject = f"New FirstView article in {journal_name}!"

        # assume email alert has not been sent yet
        alert_sent = False

        # setup IMAP4 connection
        imap = self.login_imap(self.sender_user, self.sender_authfile)

        # check email inbox
        status, messages = imap.select("INBOX")

        # select top 100 emails (if user gets more than 100 emails per day,
        # they should do something about it)
        N = 100

        # total number of emails in inbox
        messages = int(messages[0])

        for i in range(messages, messages - N, -1):

            # fetch the email message by ID
            res, msg = imap.fetch(str(i), "(RFC822)")

            for response in msg:

                if isinstance(response, tuple):

                    # parse a bytes email into a message object
                    msg = email.message_from_bytes(response[1])

                    try:

                        # decode email subject
                        message_subject, encoding = decode_header(msg["Subject"])[0]
                    except TypeError:

                        print('Email could not be decoded')
                        continue
                    
                    # select FirstView alert email
                    if message_subject == new_FirstView_subject:

                        # decode email date
                        message_date = pd.to_datetime(msg.get("Date"))

                        # get email body
                        body = msg.get_payload(decode=True).decode()

                        # check if this is the targeted alert
                        if (
                            message_date.strftime("%Y-%m-%d")
                            == pd.to_datetime("today").strftime("%Y-%m-%d")
                            and new_FirstView_url in body
                        ):

                            alert_sent = True

        return alert_sent

    def check_new_FirstViews(self, journal_url: str) -> None:
        """
        Check journal website for the publication of new FirstView articles.

        :param journal_url: Journal url

        :returns: None
        """

        # convert journal URL to a plain text journal name
        journal_name = self.journal_url_to_plaintext(journal_url)

        # make a GET request to journal_url
        r = requests.get(journal_url)

        # extract content
        c = r.content

        # make a soup (parse webpage)
        soup = BeautifulSoup(c, features="html.parser")

        # find element corresponding to last publication on webpage
        published_attr_li_tag = soup.find("li", attrs={"class": "published"})

        try:
            date_attr_span_tag = published_attr_li_tag.find(
                "span", attrs={"class": "date"}
            ).text
        except AttributeError:
            print(f'No publication tag could be found at {journal_url}')
            
        partlink_attr_a_tag = soup.find("a", attrs={"class": "part-link"})

        # reconstruct article URL
        article_url = "https://www.cambridge.org" + partlink_attr_a_tag.get("href")

        # extract publication date
        publication_date = pd.to_datetime(date_attr_span_tag)

        # consider article only if published today
        if publication_date.strftime("%Y-%m-%d") == pd.to_datetime("today").strftime(
            "%Y-%m-%d"
        ):

            # check if alert already has been sent for this new article
            already_sent = self.check_emails(article_url)

            # send alert if not already sent
            if not already_sent:

                # write a generic body text for email alert
                body_text = (
                    "An automated python script detected a"
                    + f" new FirstView article in {journal_name}:\n"
                    + f"{article_url}\n\n"
                )

                # build email through a MIME object
                message = MIMEText(body_text, "plain", "utf-8")
                message["From"] = self.sender_user
                message["To"] = self.sender_user
                message["Subject"] = f"New FirstView article in {journal_name}!"

                # setup SMTP connection
                s = self.login_smtp(self.sender_user, self.sender_authfile)

                # send email
                s.sendmail(
                    self.sender_user,
                    self.sender_user,
                    message.as_string(),
                )

                # terminate SMTP session and close connection
                s.quit()

        return None


if __name__ == "__main__":

    # create an instance of EmailAlert, initialize sender account
    sender = EmailAlert("sender@example.com", "/path/to/auth.txt")

    # run email alert for Journal of Glaciology and Annals of Glaciology
    # using sender acocunt
    sender.check_new_FirstViews(
        "https://www.cambridge.org/core/journals/journal-of-glaciology/firstview"
    )
    sender.check_new_FirstViews(
        "https://www.cambridge.org/core/journals/annals-of-glaciology/firstview"
    )
