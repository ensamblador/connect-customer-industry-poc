import aws_cdk as core
import aws_cdk.assertions as assertions

from agentic_cx_telco.agentic_cx_telco_stack import AgenticCxTelcoStack

# example tests. To run these tests, uncomment this file along with the example
# resource in agentic_cx_telco/agentic_cx_telco_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = AgenticCxTelcoStack(app, "agentic-cx-telco")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
