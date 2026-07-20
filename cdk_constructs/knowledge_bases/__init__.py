"""cdk_constructs.knowledge_bases — shared Q in Connect (Wisdom) knowledge base construct.

The construct (``S3KnowledgeBase``) is industry-agnostic: it provisions the KMS
key + S3 bucket + AppIntegrations DataIntegration + EXTERNAL Wisdom knowledge
base and takes everything as parameters. The KB *content* (the plain-text
entries + manifest) stays in each industry app under
``knowledge_bases/<industry>/``, and the post-deploy operational scripts
(``tag_kb_content.py`` / ``associate_guide.py``) stay there too.
"""

from cdk_constructs.knowledge_bases.knowledge_base import S3KnowledgeBase

__all__ = ["S3KnowledgeBase"]
