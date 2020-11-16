import logging
import os
import sys
from time import sleep

import boto3
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO)

acm = boto3.client('acm')
route53 = boto3.client('route53')
cloudformation = boto3.client("cloudformation")
STACK_NAME = 'api'
cert_update_attempt = 3


def check_if_cert_exists():
    response = acm.list_certificates()
    return response


def create_certificate(domain):
    response = acm.request_certificate(
        DomainName=domain,
        ValidationMethod='DNS'
    )
    return response


def retrieve_cert_cname():
    response = acm.list_certificates()
    response = acm.describe_certificate(
        CertificateArn=response['CertificateSummaryList'][0]['CertificateArn']
    )
    returned_response = {
        "Name": response['Certificate']['DomainValidationOptions'][0]['ResourceRecord']['Name'],
        "Value": response['Certificate']['DomainValidationOptions'][0]['ResourceRecord']['Value']
    }
    return returned_response


def update_record_set(action):
    cname_values = retrieve_cert_cname()
    response = cloudformation.describe_stacks(StackName=STACK_NAME)
    stack = response['Stacks'][0]
    outputs = stack['Outputs']
    hosted_zone = ""
    for item in outputs:
        if item['OutputKey'] == 'HostedZoneId':
            hosted_zone = item['OutputValue']
            logging.info('Retrieved HOSTEDZONE: {} in the Stack: {}'.format(hosted_zone, STACK_NAME))

    response = route53.change_resource_record_sets(
        HostedZoneId=hosted_zone,
        ChangeBatch={
            'Changes': [
                {
                    'Action': action,
                    'ResourceRecordSet': {
                        'Name': cname_values['Name'],
                        'Type': 'CNAME',
                        'TTL': 300,
                        'ResourceRecords': [{'Value': cname_values['Value']}]
                    },
                },
            ],
        }
    )
    logging.info('Change record set response: {}'.format(response))


def delete_certificate(domain):
    try:
        response = acm.list_certificates(
            CertificateStatuses=['ISSUED']
        )
        certs = response['CertificateSummaryList']
        for cert in certs:
            if domain == cert['DomainName']:
                acm.delete_certificate(
                    CertificateArn=cert['CertificateArn']
                )
                break
    except ClientError as e:
        logging.info(e)


def main(argv):
    try:
        if argv[1] == 'execute':
            # 1. Check if the certificate exists
            logging.info(" Check for certificate " + argv[0])
            response = check_if_cert_exists()
            exists = False
            for cert in response['CertificateSummaryList']:
                if cert['DomainName'] == argv[0]:
                    exists = True

            if not exists:
                logging.info(" Certificate does not currently exist...")
                # 2. Create certificate
                logging.info(" Create certificate for " + argv[0])
                response = create_certificate(argv[0])
                sleep(10)
                # 3. Update the record set
                update_record_set('UPSERT')
            else:
                logging.info(" Certificate already exists....")

        elif argv[1] == 'rollback':
            update_record_set('DELETE')
            delete_certificate(argv[0])
        else:
            logging.info("Unsupported action: {}".format(argv[0]))
            logging.info("Supported actions are 'execute' and 'rollback'")
            exit()


    except ClientError as e:
        logging.error(e.response['Error']['Message'])
        logging.error("Trying updating again....")
        i = 1
        # while i < cert_update_attempt:
        #     sleep(5)
        #     update_record_set('UPSERT')
        #     i += 1
        # logging.error(e.response['Error']['Message'])


if __name__ == '__main__':
    main(sys.argv[1:])
