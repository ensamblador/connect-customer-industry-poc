import aws_cdk as core
import aws_cdk.assertions as assertions

from general_localization.general_localization_stack import GeneralLocalizationStack

# example tests. To run these tests, uncomment this file along with the example
# resource in general_localization/general_localization_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = GeneralLocalizationStack(app, "general-localization")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
