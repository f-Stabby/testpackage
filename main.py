from botocore.vendored import requests

dependent_values = {}
dependent_requests = {}
responses = []


def add_dependent_value(request, destination, source):
    dependent_values[destination] = source
    dependent_requests[request.name] = destination


def edit_dependent_values(request, responses):
    for response in responses:
        for key, value in dependent_requests.items():
            if key == request.name:
                request.payload[value] = response["results"][0][dependent_values[value]]
    return request


class Request(object):
    def __init__(self, name, url, method, payload, error_code, error_message):
        self.name = name
        self.url = url
        self.method = method
        self.payload = payload
        self.error_code = error_code
        self.error_message = error_message
        self.dependent_values = {}
        self.dependent_requests = {}
        self.response = None
        self.headers = {}
        self.state = "success"

    def __str__(self):
        return self.name

    def add_dependent_value(self, request, destination, source):
        self.dependent_values[destination] = source
        self.dependent_requests[request.name] = destination

    def edit_dependent_values(self, request):
        for key, value in self.dependent_requests.items():
            if key == request.name:
                request.payload[value] = self.response["results"][0][self.dependent_values[value]]

    def make_request(self):
        if self.method == "POST":
            self.response = requests.post(self.url, headers=self.headers, json=self.payload)
        elif self.method == "GET":
            self.response = requests.get(self.url, headers=self.headers, json=self.payload)
        elif self.method == "PUT":
            self.response = requests.put(self.url, headers=self.headers, json=self.payload)
        elif self.method == "PATCH":
            self.response = requests.patch(self.url, headers=self.headers, json=self.payload)
        if self.response["return_code"] == self.error_code:
            self.state = "fail"

    def start(self):
        self.make_request()
        if self.state == "success":
            return True
        else:
            return False


def main(event, context):
    global dependent_requests
    global dependent_values
    global responses
    setup_batch = []
    first_dependent_batch = []
    second_dependent_batch = []
    check_email_exist = Request(
        "get_account_guid",
        event["hostname"] + "/v1-account/guid/account/email/read",
        "POST",
        {
            "email": event["to_email"]
        },
        "0",
        "ERROR! Email exist!!",
    )
    get_account_guid = Request(
        "get_account_guid",
        event["hostname"] + "/v1-account/guid/account/email/read",
        "POST",
        {
            "email": event["to_email"]
        },
        "1",
        "ERROR! failure to retrieve account guid!",
    )
    get_loyalty_id = Request(
        "get_loyalty_id",
        event["hostname"] + "/v1-account/guid/loyalty/read",
        "POST",
        {},
        "1",
        "Error! unable to get loyalty id"
    )
    get_email_guid = Request(
        "get_email_guid",
        event["hostname"] + "/v1-account/guid/email/read",
        "POST",
        {},
        "1",
        "ERROR! Unable to get email guid"
    )
    get_login_guid = Request(
        "get_login_guid",
        event["hostname"] + "/v1-account/guid/login/read",
        "POST",
        {},
        "1",
        "ERROR! Could not get login guid"
    )
    update_account_db = Request(
        "update_account_db",
        event["hostname"] + "/v1-email/support/email/modify",
        "PUT",
        {
            "email":event["to_email"]
        },
        "1",
        "ERROR! Failure to update account in database"
    )
    change_ams_email = Request(
        "change_ams_email",
        event["hostname"] + "/v1-loyalty/system/modify",
        "PUT",
        {
            "ext_card_type_id":"0",
            "email": event["to_email"]
        },
        "1",
        "ERROR! Failure to update email on AMS"
    )
    update_mailchimp_email = Request(
        "update_mailchimp_email",
        event["hostname"] + "/v1-email/support/email/modify",
        "PUT",
        {
            "email":event["to_email"]
        },
        "1",
        "ERROR! Could not update mailchimp email"
    )
    update_ping = Request(
        "update_ping",
        event["hostname"] + "/v1-login/support/email/modify",
        "PATCH",
        {
            "email":event["to_email"]
        },
        "1",
        "ERROR! Could not update ping"
    )
    #set dependent values of first batch
    add_dependent_value(get_loyalty_id, "account_guid", "account_guid")
    add_dependent_value(get_email_guid, "account_guid", "account_guid")
    add_dependent_value(get_login_guid, "account_guid", "account_guid")
    #set dependent values of second batch
    add_dependent_value(update_account_db, "account_guid", "account_guid")
    add_dependent_value(change_ams_email, "loyalty_card_id", "card_id")
    add_dependent_value(update_mailchimp_email, "email_guid", "email_guid")
    add_dependent_value(update_ping, "login_guid", "login_guid")
    #collect batch
    setup_batch.append(check_email_exist)
    setup_batch.append(get_account_guid)
    #execute batch
    for request in setup_batch:
        if not request.start():
            return {
                "return_code":"1",
                "return_message":request.error_message
            }
        else:
            responses.append(request.response)
    #batch processing
    edit_dependent_values(get_loyalty_id, responses)
    edit_dependent_values(get_email_guid, responses)
    edit_dependent_values(get_login_guid, responses)
    #collect batch
    first_dependent_batch.append(get_loyalty_id)
    first_dependent_batch.append(get_email_guid)
    first_dependent_batch.append(get_login_guid)
    #execute batch
    for request in first_dependent_batch:
        if not request.start():
            return {
                "return_code": "1",
                "return_message": request.error_message
            }
        else:
            responses.append(request.response)
    #batch processing
    edit_dependent_values(update_account_db, responses)
    edit_dependent_values(update_mailchimp_email, responses)
    edit_dependent_values(update_ping, responses)
    edit_dependent_values(change_ams_email, responses)
    #collect batch
    second_dependent_batch.append(update_mailchimp_email)
    second_dependent_batch.append(update_account_db)
    second_dependent_batch.append(update_ping)
    second_dependent_batch.append(change_ams_email)
    #execute batch
    for request in second_dependent_batch:
        if not request.start():
            return {
                "return_code": "1",
                "return_message": request.error_message
            }
        else:
            responses.append(request.response)
    #done!

