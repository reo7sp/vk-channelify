"""empty message

Revision ID: f5f69376d382
Revises: 
Create Date: 2017-07-09 15:30:59.186558

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f5f69376d382'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('channels',
    sa.Column('channel_id', sa.String(), nullable=False),
    sa.Column('vk_group_id', sa.String(), nullable=False),
    sa.Column('last_vk_post_id', sa.Integer(), server_default='0', nullable=False),
    sa.Column('owner_id', sa.String(), nullable=True),
    sa.Column('owner_username', sa.String(), nullable=True),
    sa.Column('hashtag_filter', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('channel_id')
    )
    op.create_table('disabled_channels',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('vk_group_id', sa.String(), nullable=True),
    sa.Column('last_vk_post_id', sa.Integer(), nullable=True),
    sa.Column('owner_id', sa.String(), nullable=True),
    sa.Column('owner_username', sa.String(), nullable=True),
    sa.Column('hashtag_filter', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('disabled_channels')
    op.drop_table('channels')
    # ### end Alembic commands ###
