from botocore.vendored import requests

dependent_values = {}
dependent_requests = {}
responses = []

#What happens if we have the same key?
#it wont work, so dont do that
# dependent_values = {
#     "card_id":"loyalty_card_id",
#     "card_id":"loyalty_other_variable"<=====this wont work, it will work if we turn dependent values into an array of tuples
# }
#
# dependent_requests = {
#     "get_loyalty_id":"card_id"
#     "get_another_endpoint":"card_id" <===== this will still work. this should be turned into an array of tuples as well
# }
#TODO CONVERT DEPENDENT REQUESTS AND VALUES TO ARRAYS OF TUPLES

def add_dependent_value(request, source, destination):
    global dependent_values
    global dependent_requests
    dependent_values[destination] = source
    dependent_requests[request.name] = destination

def edit_dependent_values(request, responses):
    try:
        dependent_requests[request.name]
        for response in responses:
                #if "loyalty_card_id" in response
                if dependent_values[dependent_requests[request.name]] in response["results"][0]:
                    #set request.payload["card_id"] to response["results"][0]["loyalty_card_id"]
                    request.payload[dependent_requests[request.name]] = response["results"][0][dependent_values[dependent_requests[request.name]]
    except:
        raise Exception("could not find a dependent request, are you sure you have formatted the batches correctly?")
    else:
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
    #takes in a request to be modified, a source name to parse from the response, and a destination name for the payload
    #this can happen at the very beginning, so threads already have their format in a global. I guess you could pass it in
    #if you really wanted to
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
    get_loyalty_id = edit_dependent_values(get_loyalty_id, responses)
    get_email_guid = edit_dependent_values(get_email_guid, responses)
    get_login_guid = edit_dependent_values(get_login_guid, responses)
    #collect batch
    first_dependent_batch.append(get_loyalty_id)
    first_dependent_batch.append(get_email_guid)
    first_dependent_batch.append(get_login_guid)
    #execute batch
    #CAN OCCUR IN THREAD!
    #or create a thread for every request, whatever works best!
    for request in first_dependent_batch:
        if not request.start():
            return {
                "return_code": "1",
                "return_message": request.error_message
            }
        else:
            responses.append(request.response)
    #batch processing
    update_account_db = edit_dependent_values(update_account_db, responses)
    update_mailchimp_email = edit_dependent_values(update_mailchimp_email, responses)
    update_ping = edit_dependent_values(update_ping, responses)
    change_ams_email = edit_dependent_values(change_ams_email, responses)
    #collect batch
    second_dependent_batch.append(update_mailchimp_email)
    second_dependent_batch.append(update_account_db)
    second_dependent_batch.append(update_ping)
    second_dependent_batch.append(change_ams_email)
    #execute batch
    #CAN OCCUR IN THREAD!
    #or create a thread for every request, whatever works best!
    #some configuration needs to be set up for threading to work, like returning to a global result set then iterating
    #over that set of results, perhaps instead of returning false from request.start() we could just iterate over the result set
    #every time, thereby introducing a method for threading to return properly in the main function
    for request in second_dependent_batch:
        if not request.start():
            return {
                "return_code": "1",
                "return_message": request.error_message
            }
        else:
            responses.append(request.response)
    #done!
    #delete the globals
    for var in globals():
        del var


